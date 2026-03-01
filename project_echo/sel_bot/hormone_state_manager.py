"""
Hormone state management with HIM API backend and in-memory cache.

Uses the HIM HTTP API for persistence while maintaining high-performance
in-memory access for frequent operations.

Architecture:
- In-memory dict cache for fast access (no I/O on decay/update)
- Background task writes dirty entries to HIM API every 5 minutes
- On startup: load latest state from HIM API into cache
- Graceful degradation: cache-only mode if HIM API unavailable
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional

import httpx

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
    Manages per-channel hormone state with in-memory cache and HIM API persistence.

    Architecture:
    - In-memory dict cache for fast access (no I/O on decay/update)
    - Background task writes dirty entries to HIM API every 5 minutes
    - On startup: load latest state from HIM API into cache
    - Graceful degradation: cache-only mode if HIM API unavailable

    Example usage:
        manager = HormoneStateManager(api_base_url="http://localhost:8000")
        await manager.start()

        # Get state (from cache or HIM API)
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
        api_base_url: str = "http://localhost:8000",
        him_root: str | None = None,  # Deprecated, kept for backward compatibility
        max_level: int = 3,  # Kept for backward compatibility
        snapshot_interval: int = SNAPSHOT_INTERVAL_SECONDS,
        store=None,  # Deprecated, kept for backward compatibility
    ) -> None:
        """
        Initialize HormoneStateManager.

        Args:
            api_base_url: Base URL for HIM API (default: http://localhost:8000)
            him_root: Deprecated - use api_base_url instead
            max_level: Deprecated - API handles pyramid levels
            snapshot_interval: Seconds between API writes (default: 300 = 5 minutes)
            store: Deprecated - use api_base_url instead
        """
        self._api_base_url = api_base_url.rstrip("/")
        self._him_available = True
        self._http_client: Optional[httpx.AsyncClient] = None
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

    async def start(self) -> None:
        """Start background persistence task and HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                base_url=self._api_base_url,
                timeout=httpx.Timeout(10.0, connect=5.0),
            )
            # Test API connectivity
            try:
                response = await self._http_client.get("/v1/snapshots", params={"limit": 1})
                if response.status_code == 200:
                    self._him_available = True
                    logger.info("HIM API connected at %s", self._api_base_url)
                else:
                    logger.warning("HIM API returned status %d - running in cache-only mode", response.status_code)
                    self._him_available = False
            except Exception as exc:
                logger.warning("HIM API unavailable (%s) - running in cache-only mode", exc)
                self._him_available = False

        if self._persist_task is None:
            self._persist_task = asyncio.create_task(self._persistence_loop())
            logger.info(
                "HormoneStateManager started with %d-second snapshot interval",
                self.snapshot_interval
            )

    async def stop(self) -> None:
        """Stop background task, flush all dirty entries, and close HTTP client."""
        if self._persist_task:
            self._persist_task.cancel()
            try:
                await self._persist_task
            except asyncio.CancelledError:
                pass

        # Final flush
        await self._flush_all_dirty()

        # Close HTTP client
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

        logger.info("HormoneStateManager stopped")

    @property
    def him_available(self) -> bool:
        """Check if HIM storage is available (not in cache-only mode)."""
        return self._him_available

    async def get_state(self, channel_id: str) -> CachedHormoneState:
        """
        Retrieve hormone state for a channel (from cache or HIM API).

        Returns default state if channel has no history.

        Args:
            channel_id: Discord channel ID

        Returns:
            CachedHormoneState with hormone vector and metadata
        """
        async with self._cache_lock:
            if channel_id in self._cache:
                return self._cache[channel_id]

            # Not in cache: try loading from HIM API
            state = await self._load_from_api(channel_id)
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
        """Write all dirty cache entries to HIM API."""
        dirty_entries: list[tuple[str, CachedHormoneState]] = []

        async with self._cache_lock:
            for channel_id, state in self._cache.items():
                if state.dirty:
                    dirty_entries.append((channel_id, state))

        if not dirty_entries:
            return

        # Write to HIM API
        success_count = 0
        for channel_id, state in dirty_entries:
            # Skip if HIM API is unavailable (state remains dirty)
            if self._http_client is None or not self._him_available:
                self._failed_flushes += 1
                continue

            try:
                await self._write_to_api(channel_id, state)
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
            logger.debug("Flushed %d/%d dirty hormone states to HIM API", success_count, len(dirty_entries))

    async def _load_from_api(self, channel_id: str) -> CachedHormoneState:
        """Load latest hormone state from HIM API, or return default."""
        if not self._him_available or self._http_client is None:
            logger.debug("HIM API unavailable, using default state for channel %s", channel_id)
            return self._default_state()

        try:
            response = await self._http_client.get(f"/v1/hormones/{channel_id}")

            if response.status_code == 404:
                return self._default_state()

            if response.status_code != 200:
                logger.warning("HIM API returned status %d for channel %s", response.status_code, channel_id)
                return self._default_state()

            data = response.json()

            # Parse API response into CachedHormoneState
            hormones = data.get("hormones", {})
            if not hormones:
                return self._default_state()

            vector = HormoneVector.from_dict(hormones)

            last_response_ts = None
            if data.get("last_response_ts"):
                try:
                    last_response_ts = dt.datetime.fromisoformat(data["last_response_ts"])
                except ValueError:
                    pass

            last_updated = dt.datetime.now(dt.timezone.utc)
            if data.get("last_updated"):
                try:
                    last_updated = dt.datetime.fromisoformat(data["last_updated"])
                except ValueError:
                    pass

            return CachedHormoneState(
                vector=vector,
                focus_topic=data.get("focus_topic"),
                energy_level=data.get("energy_level", 0.5),
                messages_since_response=data.get("messages_since_response", 0),
                last_response_ts=last_response_ts,
                last_updated=last_updated,
                dirty=False,
            )

        except Exception as exc:
            logger.warning("Failed to load hormone state from HIM API for channel %s: %s", channel_id, exc)
            self._him_available = False
            return self._default_state()

    async def _write_to_api(self, channel_id: str, state: CachedHormoneState) -> None:
        """Write hormone state to HIM API."""
        if self._http_client is None:
            return  # Skip if HTTP client is unavailable

        # Build update payload
        update_data = {
            "hormones": state.vector.to_dict(),
            "focus_topic": state.focus_topic,
            "energy_level": state.energy_level,
            "messages_since_response": state.messages_since_response,
            "last_response_ts": state.last_response_ts.isoformat() if state.last_response_ts else None,
        }

        response = await self._http_client.put(
            f"/v1/hormones/{channel_id}",
            json=update_data,
        )

        if response.status_code not in (200, 201):
            raise Exception(f"HIM API returned status {response.status_code}: {response.text}")

        logger.debug("Wrote hormone state to HIM API for channel=%s", channel_id)

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

    @property
    def him_available(self) -> bool:
        """Check if HIM API is available."""
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
            "api_base_url": self._api_base_url,
            "last_flush_time": self._last_flush_time.isoformat() if self._last_flush_time else None,
            "total_flushes": self._total_flushes,
            "failed_flushes": self._failed_flushes,
        }


class HormoneHistoryQuery:
    """Query historical hormone data from HIM API for analysis."""

    def __init__(self, api_base_url: str = "http://localhost:8000") -> None:
        """
        Initialize history query helper.

        Args:
            api_base_url: Base URL for HIM API
        """
        self._api_base_url = api_base_url.rstrip("/")
        self.stream = HORMONE_STREAM

    async def query_range(
        self,
        channel_id: str,
        start_time: dt.datetime,
        end_time: dt.datetime,
        level: int = 0,
        limit: int = 100,
    ) -> list[dict]:
        """
        Query hormone snapshots in a time range via HIM API.

        Returns list of payload dicts sorted by timestamp.

        Args:
            channel_id: Discord channel ID
            start_time: Start of time range (inclusive)
            end_time: End of time range (inclusive)
            level: Pyramid level (0=5min, 1=hourly, 2=daily, 3=weekly)
            limit: Maximum number of results

        Returns:
            List of hormone payload dicts sorted by timestamp

        Example:
            query = HormoneHistoryQuery("http://localhost:8000")
            snapshots = await query.query_range(
                "channel_123",
                datetime(2025, 12, 1),
                datetime(2025, 12, 10),
                level=1  # Hourly resolution
            )
            for snapshot in snapshots:
                print(snapshot["timestamp"], snapshot["hormones"]["dopamine"])
        """
        async with httpx.AsyncClient(base_url=self._api_base_url) as client:
            try:
                response = await client.get(
                    f"/v1/hormones/{channel_id}/history",
                    params={
                        "start": start_time.isoformat(),
                        "end": end_time.isoformat(),
                        "level": level,
                        "limit": limit,
                    },
                )

                if response.status_code != 200:
                    logger.warning("HIM API returned status %d", response.status_code)
                    return []

                return response.json()

            except Exception as exc:
                logger.warning("Failed to query hormone history: %s", exc)
                return []

    async def get_latest(self, channel_id: str) -> Optional[dict]:
        """
        Get most recent hormone snapshot via HIM API.

        Args:
            channel_id: Discord channel ID

        Returns:
            Latest hormone payload dict or None if no history
        """
        async with httpx.AsyncClient(base_url=self._api_base_url) as client:
            try:
                response = await client.get(f"/v1/hormones/{channel_id}")

                if response.status_code != 200:
                    return None

                data = response.json()
                if not data.get("hormones"):
                    return None

                return data

            except Exception as exc:
                logger.warning("Failed to get latest hormone state: %s", exc)
                return None
