"""
Episodic memory handling backed by the Hierarchical Image Memory store.

Each chat summary is encoded into a compact vector payload (no raster PNG tiles) and written into a
multi-level pyramid. We hash the embedding into stable tile coordinates so retrieval
focuses on a small region instead of scanning everything. Only these image tiles are
used for memory—no chat logs are persisted elsewhere.
"""

from __future__ import annotations

import asyncio
import base64
import datetime as dt
import hashlib
import json
import logging
import math
import re
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from blake3 import blake3
from him import HierarchicalImageMemory
from him.models import SnapshotCreate, SnapshotProvenance, TileIngestRecord, TilePayload

from .models import EpisodicMemory
from .state_manager import StateManager

logger = logging.getLogger(__name__)


def _sanitize_html(content: str) -> str:
    """
    Comprehensive 8-layer sanitization before storing in vector database.
    Prevents XSS attacks, memory poisoning, command injection, and encoding exploits.
    """
    if not content:
        return content

    # Import comprehensive sanitizer
    try:
        import sys
        from pathlib import Path
        project_root = Path(__file__).parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        from security.comprehensive_sanitization import sanitize
    except ImportError:
        logger.warning("Comprehensive sanitizer not available, using basic HTML removal")
        # Fallback to basic sanitization
        sanitized = re.sub(r'<[^>]+>', '', content)
        sanitized = re.sub(r'\bon\w+\s*=\s*["\'][^"\']*["\']', '', sanitized)
        sanitized = re.sub(r'javascript\s*:', '', sanitized, flags=re.IGNORECASE)
        return sanitized

    # Use comprehensive 8-layer sanitization
    sanitized = sanitize(content, aggressive=True)

    # Log if content was modified
    if sanitized != content:
        logger.warning(
            f"Comprehensive sanitization applied to memory content: "
            f"{content[:50]}... -> {sanitized[:50]}..."
        )

    return sanitized


MEMORY_STREAM = "episodic_vector"
MEMORY_DTYPE = "vector/json;memory_v3"


def _token_hash(token: str) -> float:
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(digest, "little") / 2**32


def generate_embedding(text: str, dim: int = 12) -> List[float]:
    tokens = text.lower().split()
    if not tokens:
        return [0.0] * dim
    vector = [0.0] * dim
    for tok in tokens:
        idx = int(_token_hash(tok) * dim) % dim
        vector[idx] += 1.0
    norm = (sum(x * x for x in vector) or 1.0) ** 0.5
    return [x / norm for x in vector]


def embedding_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _now() -> dt.datetime:
    return dt.datetime.now(tz=dt.timezone.utc)


def _coords_for_level(embedding: Sequence[float], level: int) -> tuple[int, int, int]:
    """
    Map an embedding to a stable tile coordinate for the requested level.
    """

    digest = hashlib.blake2b(
        json.dumps(list(embedding), sort_keys=True).encode("utf-8"),
        digest_size=8,
        person=b"sel-mem",
    ).digest()
    tile_count = max(1, 1 << max(level, 0))
    x = int.from_bytes(digest[:4], "little") % tile_count
    y = int.from_bytes(digest[4:], "little") % tile_count
    return x, y, tile_count


def _bbox_for_level(embedding: Sequence[float], level: int, radius: int = 1) -> tuple[int, int, int, int]:
    x, y, tile_count = _coords_for_level(embedding, level)
    span = max(0, radius)
    x0 = max(0, x - span)
    y0 = max(0, y - span)
    width = min(tile_count - x0, (span * 2) + 1)
    height = min(tile_count - y0, (span * 2) + 1)
    return x0, y0, width, height


def _compute_tile_id(stream: str, snapshot_id: str, level: int, x: int, y: int, payload_bytes: bytes) -> str:
    digest = blake3()
    for part in (stream, snapshot_id, str(level), str(x), str(y)):
        digest.update(part.encode("utf-8"))
    digest.update(payload_bytes)
    return digest.hexdigest()


def _encode_payload_vector(
    *,
    summary: str,
    tags: Iterable[str],
    embedding: Sequence[float],
    salience: float,
    timestamp: dt.datetime,
) -> bytes:
    """
    Encode memory content as a small vector scene: circles on a unit canvas representing the embedding,
    plus metadata preserved for decoding. Kept JSON-based but intentionally used as a vector payload type.
    """

    shapes = []
    dims = list(embedding)
    for idx, value in enumerate(dims):
        radius = max(0.05, min(0.4, abs(value) * 0.6))
        angle = (idx / max(1, len(dims))) * 2 * math.pi
        cx = 0.5 + math.cos(angle) * 0.3 * value
        cy = 0.5 + math.sin(angle) * 0.3 * value
        intensity = max(0.0, min(1.0, (value + 1) / 2))
        color = f"#{int(255 * intensity):02x}{int(180 * (1 - intensity)):02x}{int(200 * salience):02x}"
        shapes.append(
            {
                "kind": "circle",
                "center": [cx, cy],
                "radius": radius,
                "stroke": color,
                "fill": color,
                "weight": salience,
            }
        )

    payload = {
        "format": "episodic_vector_v1",
        "summary": summary,
        "tags": list(tags),
        "embedding": list(embedding),
        "salience": float(salience),
        "timestamp": timestamp.isoformat(),
        "shapes": shapes,
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")


def _decode_payload_vector(raw: bytes) -> dict:
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}


class MemoryManager:
    def __init__(
        self,
        state_manager: Optional[StateManager],
        *,
        him_root: str | Path = Path("sel_data/him_store"),
        max_level: int = 3,
        provenance: Optional[SnapshotProvenance] = None,
        store: HierarchicalImageMemory | None = None,
    ) -> None:
        self.state_manager = state_manager
        self.store = store or HierarchicalImageMemory(Path(him_root))
        self.max_level = max(1, max_level)
        self.stream = MEMORY_STREAM
        self._provenance = provenance or SnapshotProvenance(
            model="sel-memory",
            code_sha="local",
        )
        # Deduplication cache: store recent memory hashes to prevent duplicates
        # Format: {(channel_id, summary_hash): timestamp}
        self._recent_memories: dict[tuple[str, str], dt.datetime] = {}

    async def maybe_store(
        self,
        channel_id: str,
        summary: str,
        tags: Iterable[str] | None = None,
        salience: float = 0.5,
        timestamp: dt.datetime | None = None,
    ) -> EpisodicMemory:
        """
        Store a summary across the HIM pyramid and return an in-memory representation.
        """

        # SECURITY: Sanitize HTML/JavaScript before storing in vector database
        summary = _sanitize_html(summary)

        return self._store_sync(
            channel_id,
            summary,
            tags or (),
            salience,
            timestamp,
        )

    def _store_sync(
        self,
        channel_id: str,
        summary: str,
        tags: Iterable[str],
        salience: float,
        timestamp: dt.datetime | None = None,
    ) -> EpisodicMemory:
        snapshot_id = str(channel_id)
        embedding = generate_embedding(summary)
        if timestamp is None:
            timestamp = _now()
        elif timestamp.tzinfo is None:
            # Ensure timezone-aware
            timestamp = timestamp.replace(tzinfo=dt.timezone.utc)

        # Persistent deduplication: check database for identical summary in last 24 hours
        if self.store.snapshot_exists(snapshot_id):
            cutoff_time = timestamp - dt.timedelta(hours=24)
            existing_tiles = self.store.tiles_for_snapshot(
                snapshot_id,
                stream=self.stream,
                level_range=(0, 0),  # Only check L0 (base level)
            )

            # Check if any recent tile has the same summary
            for tile_meta in existing_tiles:
                try:
                    stored_tile = self.store.get_tile(tile_meta.tile_id)
                    payload = _decode_payload_vector(stored_tile.payload_path.read_bytes())
                    if isinstance(payload, dict):
                        existing_summary = payload.get('summary', '')
                        existing_timestamp_str = payload.get('timestamp')

                        if existing_summary == summary and existing_timestamp_str:
                            try:
                                existing_timestamp = dt.datetime.fromisoformat(existing_timestamp_str)
                                if existing_timestamp > cutoff_time:
                                    logger.info(f"Skipping duplicate memory (found in DB): {summary[:50]}")
                                    return EpisodicMemory(
                                        channel_id=snapshot_id,
                                        summary=summary,
                                        tags=list(tags),
                                        embedding=list(embedding),
                                        salience=salience,
                                        timestamp=existing_timestamp,
                                    )
                            except (ValueError, TypeError):
                                pass
                except Exception:
                    continue

        # Clean in-memory cache (keep last 100, remove entries older than 5 minutes)
        cutoff = timestamp - dt.timedelta(minutes=5)
        self._recent_memories = {
            k: v for k, v in self._recent_memories.items()
            if v > cutoff
        }
        if len(self._recent_memories) > 100:
            sorted_items = sorted(self._recent_memories.items(), key=lambda x: x[1], reverse=True)
            self._recent_memories = dict(sorted_items[:100])
        payload_bytes = _encode_payload_vector(
            summary=summary,
            tags=tags,
            embedding=embedding,
            salience=salience,
            timestamp=timestamp,
        )
        self._ensure_snapshot(snapshot_id)
        records = self._build_tile_records(snapshot_id, embedding, payload_bytes)
        metas = self.store.put_tiles(records)
        logger.debug(
            "Stored %d HIM tiles for channel=%s snapshot=%s levels=%s",
            len(metas),
            channel_id,
            snapshot_id,
            [m.level for m in metas],
        )
        return EpisodicMemory(
            channel_id=snapshot_id,
            summary=summary,
            tags=list(tags),
            embedding=list(embedding),
            salience=salience,
            timestamp=timestamp,
        )

    async def retrieve(self, channel_id: str, query: str, limit: int = 10) -> List[EpisodicMemory]:
        """
        Query hierarchical tiles for the closest episodic memories.
        """

        return self._retrieve_sync(channel_id, query, limit)

    def _retrieve_sync(self, channel_id: str, query: str, limit: int) -> List[EpisodicMemory]:
        snapshot_id = str(channel_id)
        if not self.store.snapshot_exists(snapshot_id):
            return []

        # Extract keywords from query for fast filtering
        keywords = [w.lower() for w in query.split() if len(w) > 3][:5]  # Top 5 words > 3 chars

        query_vec = generate_embedding(query)
        seen: set[str] = set()
        seen_summaries: set[str] = set()  # Deduplicate by content
        candidates: list[tuple[float, EpisodicMemory]] = []
        all_memories: list[EpisodicMemory] = []

        # Collect all memories with keyword pre-filtering
        for level in range(self.max_level, -1, -1):
            metas = self.store.tiles_for_snapshot(
                snapshot_id,
                stream=self.stream,
                level_range=(level, level),
            )
            for meta in metas:
                if meta.tile_id in seen:
                    continue
                seen.add(meta.tile_id)
                try:
                    stored = self.store.get_tile(meta.tile_id)
                    payload_bytes = _decode_payload_vector(stored.payload_path.read_bytes())
                    payload = payload_bytes if isinstance(payload_bytes, dict) else {}
                except Exception as exc:
                    logger.warning("HIM tile missing or unreadable channel=%s tile=%s: %s", channel_id, meta.tile_id, exc)
                    continue
                mem = self._payload_to_memory(channel_id, payload)

                # Skip duplicate summaries (same content stored at multiple levels)
                if mem.summary in seen_summaries:
                    continue
                seen_summaries.add(mem.summary)

                # Keyword filter: if we have keywords, only process memories that match
                if keywords:
                    summary_lower = mem.summary.lower()
                    has_keyword = any(kw in summary_lower for kw in keywords)
                    if has_keyword:
                        all_memories.append((mem, level))
                else:
                    all_memories.append((mem, level))

        # If keyword filtering gave us too few results, use all memories
        min_candidates = limit * 3
        if len(all_memories) < min_candidates:
            logger.info(f"Keyword filter returned {len(all_memories)} memories, using all tiles")
            all_memories = []
            seen.clear()
            seen_summaries.clear()  # Reset summary deduplication
            for level in range(self.max_level, -1, -1):
                metas = self.store.tiles_for_snapshot(
                    snapshot_id,
                    stream=self.stream,
                    level_range=(level, level),
                )
                for meta in metas:
                    if meta.tile_id in seen:
                        continue
                    seen.add(meta.tile_id)
                    try:
                        stored = self.store.get_tile(meta.tile_id)
                        payload_bytes = _decode_payload_vector(stored.payload_path.read_bytes())
                        payload = payload_bytes if isinstance(payload_bytes, dict) else {}
                    except Exception:
                        continue
                    mem = self._payload_to_memory(channel_id, payload)

                    # Skip duplicate summaries here too
                    if mem.summary in seen_summaries:
                        continue
                    seen_summaries.add(mem.summary)

                    all_memories.append((mem, level))

        # Score all collected memories by semantic similarity + recency
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)

        for mem, level in all_memories:
            similarity = embedding_similarity(query_vec, mem.embedding or generate_embedding(mem.summary))
            score = similarity
            score += (mem.salience or 0.5) * 0.2
            score += level * 0.05

            # Add strong recency bonus - only very recent memories get boosted
            if mem.timestamp:
                age_days = (now - mem.timestamp).total_seconds() / 86400
                # Aggressive decay: only last few days matter, old gets penalized
                if age_days < 1:
                    recency_bonus = 0.4  # Today = massive boost
                elif age_days < 3:
                    recency_bonus = 0.25  # Last 3 days = big boost
                elif age_days < 7:
                    recency_bonus = 0.1  # Last week = small boost
                else:
                    # Anything older than a week gets penalized
                    recency_bonus = -0.1 * min(age_days / 7, 3)  # Max penalty -0.3 for very old
                score += recency_bonus

            candidates.append((score, mem))

        candidates.sort(key=lambda x: x[0], reverse=True)
        return [mem for _, mem in candidates[:limit]]

    def _build_tile_records(
        self,
        snapshot_id: str,
        embedding: Sequence[float],
        payload_bytes: bytes,
    ) -> list[TileIngestRecord]:
        encoded_payload = base64.b64encode(payload_bytes).decode("utf-8")
        records: list[TileIngestRecord] = []
        parent_tile_id = None
        for level in range(0, self.max_level + 1):
            x, y, _ = _coords_for_level(embedding, level)
            tile_id = _compute_tile_id(self.stream, snapshot_id, level, x, y, payload_bytes)
            record = TileIngestRecord(
                stream=self.stream,
                snapshot_id=snapshot_id,
                level=level,
                x=x,
                y=y,
                shape=(1, 1, 1),
                dtype=MEMORY_DTYPE,
                payload=TilePayload(bytes_b64=encoded_payload),
                halo=None,
                parent_tile_id=parent_tile_id,
            )
            records.append(record)
            parent_tile_id = tile_id
        return records

    def _ensure_snapshot(self, snapshot_id: str) -> None:
        if self.store.snapshot_exists(snapshot_id):
            return
        payload = SnapshotCreate(
            snapshot_id=snapshot_id,
            parents=[],
            tags={"channel_id": snapshot_id},
            provenance=self._provenance,
        )
        self.store.create_snapshot(payload)
        logger.info("Created HIM snapshot for channel=%s", snapshot_id)

    @staticmethod
    def _payload_to_memory(channel_id: str, payload: dict) -> EpisodicMemory:
        summary = str(payload.get("summary") or "").strip()
        tags = payload.get("tags") or []
        salience = float(payload.get("salience", 0.5))
        embedding = payload.get("embedding") or generate_embedding(summary)
        ts_raw = payload.get("timestamp")
        timestamp: dt.datetime | None = None
        if isinstance(ts_raw, str):
            try:
                timestamp = dt.datetime.fromisoformat(ts_raw)
            except ValueError:
                timestamp = None
        return EpisodicMemory(
            channel_id=str(channel_id),
            summary=summary,
            tags=list(tags),
            embedding=list(embedding),
            salience=salience,
            timestamp=timestamp or _now(),
        )
