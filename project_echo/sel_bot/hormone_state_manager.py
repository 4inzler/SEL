"""
Hormone state management with HIM backend and in-memory cache.

Replaces SQLAlchemy hormone storage with HIM tiles while maintaining
high-performance in-memory access for frequent operations.

Architecture:
- In-memory dict cache for fast access (no I/O on decay/update)
- Background task writes dirty entries to HIM every 5 minutes
- On startup: load latest tiles from HIM into cache
- Graceful degradation: cache-only mode if HIM unavailable
"""

from __future__ import annotations

import asyncio
import base64
import datetime as dt
import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from blake3 import blake3

from sel_bot.hormones import HormoneVector

logger = logging.getLogger(__name__)

HORMONE_STREAM = "hormonal_state"
HORMONE_DTYPE = "hormonal_vector/json;v1"
SNAPSHOT_INTERVAL_SECONDS = 300  # 5 minutes


@dataclass
class CachedHormoneState:
    """In-memory hormone state with metadata."""

    vector: HormoneVector
    focus_topic: Optional[str] = None
    energy_level: float = 0.5
    messages_since_response: int = 0
    last_response_ts: Optional[dt.datetime] = None
    last_updated: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
    dirty: bool = False  # True if modified since last HIM write


class HormoneStateManager:
    """
    Manages per-channel hormone state with in-memory cache and HIM persistence.

    Architecture:
    - In-memory dict cache for fast access (no I/O on decay/update)
    - Background task writes dirty entries to HIM every 5 minutes
    - On startup: load latest tiles from HIM into cache
    - Graceful degradation: cache-only mode if HIM unavailable

    Example usage:
        manager = HormoneStateManager(him_root="sel_data/him_store")
        await manager.start()

        # Get state (from cache or HIM)
        state = await manager.get_state("channel_123")

        # Update state (in-memory, marks dirty)
        state.vector.dopamine = 0.8
        await manager.update_state("channel_123", state.vector)

        # Background task flushes dirty entries every 5 minutes
        await manager.stop()  # Final flush on shutdown
    """

    def __init__(
        self,
        *,
        him_root: str | Path = Path("sel_data/him_store"),
        max_level: int = 3,
        snapshot_interval: int = SNAPSHOT_INTERVAL_SECONDS,
        store = None,  # HierarchicalImageMemory instance
    ) -> None:
        """
        Initialize HormoneStateManager.

        Args:
            him_root: Root directory for HIM storage
            max_level: Maximum pyramid level (0 = finest, 3 = coarsest)
            snapshot_interval: Seconds between HIM writes (default: 300 = 5 minutes)
            store: Optional HierarchicalImageMemory instance (for testing)
        """
        # Lazy import to avoid circular dependencies
        self._him_available = True
        if store is None:
            try:
                from him import HierarchicalImageMemory
                self.store = HierarchicalImageMemory(Path(him_root))
            except Exception as exc:
                logger.warning("Failed to initialize HIM storage: %s - running in cache-only mode", exc)
                self.store = None
                self._him_available = False
        else:
            self.store = store

        self.max_level = max(1, max_level)
        self.snapshot_interval = snapshot_interval
        self.stream = HORMONE_STREAM

        # In-memory cache: channel_id -> CachedHormoneState
        self._cache: Dict[str, CachedHormoneState] = {}
        self._cache_lock = asyncio.Lock()

        # Background persistence task
        self._persist_task: Optional[asyncio.Task] = None

        # Metrics
        self._last_flush_time: Optional[dt.datetime] = None
        self._total_flushes = 0
        self._failed_flushes = 0

        # Provenance for snapshot creation
        try:
            from him.models import SnapshotProvenance
            self._provenance = SnapshotProvenance(
                model="sel-hormone-state",
                code_sha="local",
            )
        except ImportError:
            logger.warning("Could not import SnapshotProvenance, using None")
            self._provenance = None

    async def start(self) -> None:
        """Start background persistence task."""
        if self._persist_task is None:
            self._persist_task = asyncio.create_task(self._persistence_loop())
            logger.info(
                "HormoneStateManager started with %d-second snapshot interval",
                self.snapshot_interval
            )

    async def stop(self) -> None:
        """Stop background task and flush all dirty entries."""
        if self._persist_task:
            self._persist_task.cancel()
            try:
                await self._persist_task
            except asyncio.CancelledError:
                pass

        # Final flush
        await self._flush_all_dirty()
        logger.info("HormoneStateManager stopped")

    @property
    def him_available(self) -> bool:
        """Check if HIM storage is available (not in cache-only mode)."""
        return self._him_available

    async def get_state(self, channel_id: str) -> CachedHormoneState:
        """
        Retrieve hormone state for a channel (from cache or HIM).

        Returns default state if channel has no history.

        Args:
            channel_id: Discord channel ID

        Returns:
            CachedHormoneState with hormone vector and metadata
        """
        async with self._cache_lock:
            if channel_id in self._cache:
                return self._cache[channel_id]

            # Not in cache: try loading from HIM
            state = await self._load_from_him(channel_id)
            self._cache[channel_id] = state
            return state

    async def update_state(
        self,
        channel_id: str,
        vector: HormoneVector,
        *,
        focus_topic: Optional[str] = None,
        energy_level: Optional[float] = None,
        messages_since_response: Optional[int] = None,
        last_response_ts: Optional[dt.datetime] = None,
    ) -> CachedHormoneState:
        """
        Update hormone state in cache (marks as dirty for persistence).

        Updates are in-memory only; persistence happens in background.

        Args:
            channel_id: Discord channel ID
            vector: Updated hormone vector
            focus_topic: Optional current focus topic
            energy_level: Optional energy level (0.0-1.0)
            messages_since_response: Optional message count
            last_response_ts: Optional last response timestamp

        Returns:
            Updated CachedHormoneState
        """
        async with self._cache_lock:
            state = self._cache.get(channel_id)
            if state is None:
                # Create new state
                state = CachedHormoneState(
                    vector=vector,
                    focus_topic=focus_topic,
                    energy_level=energy_level or 0.5,
                    messages_since_response=messages_since_response or 0,
                    last_response_ts=last_response_ts,
                )
            else:
                # Update existing
                state.vector = vector
                if focus_topic is not None:
                    state.focus_topic = focus_topic
                if energy_level is not None:
                    state.energy_level = energy_level
                if messages_since_response is not None:
                    state.messages_since_response = messages_since_response
                if last_response_ts is not None:
                    state.last_response_ts = last_response_ts

            state.last_updated = dt.datetime.now(dt.timezone.utc)
            state.dirty = True
            self._cache[channel_id] = state
            return state

    async def _persistence_loop(self) -> None:
        """Background task: persist dirty cache entries to HIM."""
        while True:
            try:
                await asyncio.sleep(self.snapshot_interval)
                await self._flush_all_dirty()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Persistence loop error: %s", exc)
                # Mark HIM as unavailable on repeated failures
                self._him_available = False
                self._failed_flushes += 1

    async def _flush_all_dirty(self) -> None:
        """Write all dirty cache entries to HIM."""
        dirty_entries: list[tuple[str, CachedHormoneState]] = []

        async with self._cache_lock:
            for channel_id, state in self._cache.items():
                if state.dirty:
                    dirty_entries.append((channel_id, state))

        if not dirty_entries:
            return

        # Write to HIM (synchronous, outside lock)
        success_count = 0
        for channel_id, state in dirty_entries:
            # Skip if HIM is unavailable (state remains dirty)
            if self.store is None or not self._him_available:
                self._failed_flushes += 1
                continue

            try:
                await self._write_to_him(channel_id, state)
                # Clear dirty flag after successful write
                async with self._cache_lock:
                    if channel_id in self._cache:
                        self._cache[channel_id].dirty = False
                success_count += 1
                self._him_available = True
            except Exception as exc:
                logger.warning("Failed to persist hormone state for channel %s: %s", channel_id, exc)
                self._him_available = False
                self._failed_flushes += 1
                # State remains dirty for retry on next loop

        if success_count > 0:
            self._last_flush_time = dt.datetime.now(dt.timezone.utc)
            self._total_flushes += 1
            logger.debug("Flushed %d/%d dirty hormone states to HIM", success_count, len(dirty_entries))

    async def _load_from_him(self, channel_id: str) -> CachedHormoneState:
        """Load latest hormone state from HIM, or return default."""
        if not self._him_available or self.store is None:
            logger.debug("HIM unavailable, using default state for channel %s", channel_id)
            return self._default_state()

        snapshot_id = str(channel_id)

        try:
            # Check if snapshot exists
            if not self.store.snapshot_exists(snapshot_id):
                return self._default_state()

            # Find latest tile at level 0 (finest resolution)
            metas = self.store.tiles_for_snapshot(
                snapshot_id,
                stream=self.stream,
                level_range=(0, 0),  # Only level 0
            )

            if not metas:
                return self._default_state()

            # Sort by x coordinate (time bucket) descending to get latest
            metas_sorted = sorted(metas, key=lambda m: m.x, reverse=True)
            latest_meta = metas_sorted[0]

            # Load tile payload
            stored = self.store.get_tile(latest_meta.tile_id)
            payload_data = json.loads(stored.payload_path.read_bytes().decode("utf-8"))

            # Parse into CachedHormoneState
            return self._payload_to_state(payload_data)

        except Exception as exc:
            logger.warning("Failed to load hormone state from HIM for channel %s: %s", channel_id, exc)
            self._him_available = False
            return self._default_state()

    async def _write_to_him(self, channel_id: str, state: CachedHormoneState) -> None:
        """Write hormone state to HIM as tiles."""
        if self.store is None:
            return  # Skip if HIM is unavailable

        snapshot_id = str(channel_id)
        timestamp = state.last_updated

        # Ensure snapshot exists
        self._ensure_snapshot(snapshot_id)

        # Generate payload
        payload_bytes = self._state_to_payload_bytes(channel_id, state, timestamp)

        # Build tile records for all levels
        records = self._build_tile_records(snapshot_id, timestamp, payload_bytes)

        # Write to HIM
        metas = self.store.put_tiles(records)
        logger.debug(
            "Wrote %d HIM tiles for channel=%s levels=%s",
            len(metas),
            channel_id,
            [m.level for m in metas],
        )

    def _state_to_payload_bytes(
        self,
        channel_id: str,
        state: CachedHormoneState,
        timestamp: dt.datetime,
    ) -> bytes:
        """Serialize hormone state to JSON payload bytes."""
        time_bucket = int(timestamp.timestamp()) // self.snapshot_interval

        # Extract hormone values using to_dict() method
        hormones = state.vector.to_dict()

        # Generate visual shapes for HIM compatibility
        shapes = self._generate_shapes(hormones)

        payload = {
            "format": "hormonal_state_v1",
            "channel_id": channel_id,
            "timestamp": timestamp.isoformat(),
            "time_bucket": time_bucket,
            "hormones": hormones,
            "metadata": {
                "focus_topic": state.focus_topic,
                "energy_level": state.energy_level,
                "messages_since_response": state.messages_since_response,
                "last_response_ts": state.last_response_ts.isoformat() if state.last_response_ts else None,
            },
            "shapes": shapes,
        }

        return json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")

    def _payload_to_state(self, payload: dict) -> CachedHormoneState:
        """Deserialize JSON payload to CachedHormoneState."""
        hormones = payload.get("hormones", {})
        metadata = payload.get("metadata", {})

        # Use from_dict() method to reconstruct hormone vector
        vector = HormoneVector.from_dict(hormones)

        last_response_ts = None
        if metadata.get("last_response_ts"):
            try:
                last_response_ts = dt.datetime.fromisoformat(metadata["last_response_ts"])
            except ValueError:
                pass

        timestamp_str = payload.get("timestamp")
        last_updated = dt.datetime.now(dt.timezone.utc)
        if timestamp_str:
            try:
                last_updated = dt.datetime.fromisoformat(timestamp_str)
            except ValueError:
                pass

        return CachedHormoneState(
            vector=vector,
            focus_topic=metadata.get("focus_topic"),
            energy_level=metadata.get("energy_level", 0.5),
            messages_since_response=metadata.get("messages_since_response", 0),
            last_response_ts=last_response_ts,
            last_updated=last_updated,
            dirty=False,  # Just loaded, not dirty
        )

    def _build_tile_records(
        self,
        snapshot_id: str,
        timestamp: dt.datetime,
        payload_bytes: bytes,
    ) -> list:
        """Build tile records for all pyramid levels."""
        # Lazy import to avoid circular dependencies
        from him.models import TileIngestRecord, TilePayload

        encoded_payload = base64.b64encode(payload_bytes).decode("utf-8")
        records: list = []
        parent_tile_id = None

        for level in range(0, self.max_level + 1):
            x, y = self._time_bucket_to_coords(timestamp, level)
            tile_id = self._compute_tile_id(self.stream, snapshot_id, level, x, y, payload_bytes)

            record = TileIngestRecord(
                stream=self.stream,
                snapshot_id=snapshot_id,
                level=level,
                x=x,
                y=y,
                shape=(1, 1, 1),
                dtype=HORMONE_DTYPE,
                payload=TilePayload(bytes_b64=encoded_payload),
                halo=None,
                parent_tile_id=parent_tile_id,
            )
            records.append(record)
            parent_tile_id = tile_id

        return records

    def _time_bucket_to_coords(self, timestamp: dt.datetime, level: int) -> tuple[int, int]:
        """
        Map timestamp to tile coordinates for hierarchical storage.

        Level 0 (finest): 5-minute buckets
        Level 1: 1-hour buckets (12x aggregation)
        Level 2: 1-day buckets (288x aggregation)
        Level 3: 1-week buckets (2016x aggregation)

        x = time bucket index (continuous timeline)
        y = 0 (single row, all temporal data on x-axis)
        """
        epoch = int(timestamp.timestamp())

        if level == 0:
            bucket = epoch // 300  # 5 minutes
        elif level == 1:
            bucket = epoch // 3600  # 1 hour
        elif level == 2:
            bucket = epoch // 86400  # 1 day
        else:
            bucket = epoch // 604800  # 1 week

        x = bucket % (2**31)  # Prevent overflow
        y = 0  # Single row per channel
        return x, y

    def _compute_tile_id(
        self,
        stream: str,
        snapshot_id: str,
        level: int,
        x: int,
        y: int,
        payload_bytes: bytes,
    ) -> str:
        """Compute content-addressed tile ID using blake3."""
        digest = blake3()
        for part in (stream, snapshot_id, str(level), str(x), str(y)):
            digest.update(part.encode("utf-8"))
        digest.update(payload_bytes)
        return digest.hexdigest()

    def _ensure_snapshot(self, snapshot_id: str) -> None:
        """Ensure HIM snapshot exists for channel."""
        if self.store is None:
            return  # Skip if HIM is unavailable
        if self.store.snapshot_exists(snapshot_id):
            return

        # Lazy import to avoid circular dependencies
        from him.models import SnapshotCreate

        payload = SnapshotCreate(
            snapshot_id=snapshot_id,
            parents=[],
            tags={"channel_id": snapshot_id, "type": "hormonal_state"},
            provenance=self._provenance,
        )
        self.store.create_snapshot(payload)
        logger.info("Created HIM snapshot for hormone state: channel=%s", snapshot_id)

    @staticmethod
    def _default_state() -> CachedHormoneState:
        """Return default hormone state for new channels."""
        return CachedHormoneState(
            vector=HormoneVector(),  # Uses defaults from dataclass
            focus_topic=None,
            energy_level=0.5,
            messages_since_response=0,
            last_response_ts=None,
            dirty=False,
        )

    @staticmethod
    def _generate_shapes(hormones: dict) -> list[dict]:
        """Generate visual shapes for HIM tile visualization."""
        shapes = []
        hormone_list = list(hormones.items())

        for idx, (name, value) in enumerate(hormone_list):
            # Map hormone to circle on unit canvas
            angle = (idx / max(1, len(hormone_list))) * 2 * math.pi
            radius = max(0.05, min(0.15, abs(value) * 0.4))
            cx = 0.5 + math.cos(angle) * 0.35 * value
            cy = 0.5 + math.sin(angle) * 0.35 * value

            # Color based on value
            intensity = max(0.0, min(1.0, (value + 1.0) / 2.0))
            color = f"#{int(255 * intensity):02x}{int(180 * (1 - intensity)):02x}{int(200 * abs(value)):02x}"

            shapes.append({
                "kind": "circle",
                "center": [cx, cy],
                "radius": radius,
                "stroke": color,
                "fill": color,
                "hormone": name,
                "value": value,
            })

        return shapes

    @property
    def him_available(self) -> bool:
        """Check if HIM backend is available."""
        return self._him_available

    def get_metrics(self) -> dict:
        """
        Return current manager metrics for monitoring.

        Returns:
            Dict with cache_size, dirty_count, him_available, flush stats
        """
        dirty_count = sum(1 for s in self._cache.values() if s.dirty)
        return {
            "cache_size": len(self._cache),
            "dirty_count": dirty_count,
            "him_available": self._him_available,
            "last_flush_time": self._last_flush_time.isoformat() if self._last_flush_time else None,
            "total_flushes": self._total_flushes,
            "failed_flushes": self._failed_flushes,
        }


class HormoneHistoryQuery:
    """Query historical hormone data from HIM for analysis."""

    def __init__(self, store) -> None:
        """
        Initialize history query helper.

        Args:
            store: HierarchicalImageMemory instance
        """
        self.store = store
        self.stream = HORMONE_STREAM

    def query_range(
        self,
        channel_id: str,
        start_time: dt.datetime,
        end_time: dt.datetime,
        level: int = 0,
    ) -> list[dict]:
        """
        Query hormone snapshots in a time range.

        Returns list of payload dicts sorted by timestamp.

        Args:
            channel_id: Discord channel ID
            start_time: Start of time range (inclusive)
            end_time: End of time range (inclusive)
            level: Pyramid level (0=5min, 1=hourly, 2=daily, 3=weekly)

        Returns:
            List of hormone payload dicts sorted by timestamp

        Example:
            query = HormoneHistoryQuery(him_store)
            snapshots = query.query_range(
                "channel_123",
                datetime(2025, 12, 1),
                datetime(2025, 12, 10),
                level=1  # Hourly resolution
            )
            for snapshot in snapshots:
                print(snapshot["timestamp"], snapshot["hormones"]["dopamine"])
        """
        snapshot_id = str(channel_id)

        if not self.store.snapshot_exists(snapshot_id):
            return []

        # Calculate time bucket range using HormoneStateManager logic
        manager = HormoneStateManager(store=self.store)
        x_start, _ = manager._time_bucket_to_coords(start_time, level)
        x_end, _ = manager._time_bucket_to_coords(end_time, level)

        # Query tiles in range
        metas = self.store.tiles_for_snapshot(
            snapshot_id,
            stream=self.stream,
            level_range=(level, level),
        )

        # Filter by x coordinate (time bucket)
        filtered = [m for m in metas if x_start <= m.x <= x_end]

        # Load payloads
        results = []
        for meta in filtered:
            try:
                stored = self.store.get_tile(meta.tile_id)
                payload = json.loads(stored.payload_path.read_bytes().decode("utf-8"))
                results.append(payload)
            except Exception as exc:
                logger.warning("Failed to load tile %s: %s", meta.tile_id, exc)

        # Sort by timestamp
        results.sort(key=lambda p: p.get("timestamp", ""))
        return results

    def get_latest(self, channel_id: str) -> Optional[dict]:
        """
        Get most recent hormone snapshot.

        Args:
            channel_id: Discord channel ID

        Returns:
            Latest hormone payload dict or None if no history
        """
        snapshot_id = str(channel_id)

        if not self.store.snapshot_exists(snapshot_id):
            return None

        metas = self.store.tiles_for_snapshot(
            snapshot_id,
            stream=self.stream,
            level_range=(0, 0),
        )

        if not metas:
            return None

        # Latest by x coordinate (time bucket)
        latest = max(metas, key=lambda m: m.x)

        try:
            stored = self.store.get_tile(latest.tile_id)
            return json.loads(stored.payload_path.read_bytes().decode("utf-8"))
        except Exception as exc:
            logger.warning("Failed to load latest tile: %s", exc)
            return None
