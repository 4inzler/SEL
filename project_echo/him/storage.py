"""Storage primitives for the Hierarchical Image Memory system."""
from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from blake3 import blake3

from .models import QueryHint, Snapshot, SnapshotCreate, TileIngestRecord, TileMeta


@dataclass(slots=True)
class StoredTile:
    """Serialized representation of a tile on disk."""

    metadata: TileMeta
    payload_path: Path


@dataclass(slots=True)
class TileUsage:
    """Book-keeping information describing tile hotness."""

    access_count: int
    last_access: Optional[datetime]


DB_FILE = "him.db"


class HierarchicalImageMemory:
    """SQLite-backed implementation of the Hierarchical Image Memory store."""

    def __init__(self, root: Path | str = Path("data")) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._db_path = self.root / DB_FILE
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    # ------------------------------------------------------------------
    # Snapshot management
    # ------------------------------------------------------------------
    def create_snapshot(self, payload: SnapshotCreate) -> Snapshot:
        with self._lock:
            if self._snapshot_exists(payload.snapshot_id):
                raise ValueError(f"Snapshot '{payload.snapshot_id}' already exists")

            created_at = self._utcnow()
            self._conn.execute(
                """
                INSERT INTO snapshots (snapshot_id, parents, created_at, tags, provenance, merge_policy)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.snapshot_id,
                    json.dumps(payload.parents),
                    created_at.isoformat(),
                    json.dumps(payload.tags),
                    json.dumps(payload.provenance.model_dump(mode="json")),
                    payload.merge_policy.value,
                ),
            )
            self._conn.commit()
        return self.get_snapshot(payload.snapshot_id)

    def get_snapshot(self, snapshot_id: str) -> Snapshot:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM snapshots WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Snapshot '{snapshot_id}' not found")
        return self._row_to_snapshot(row)

    def list_snapshots(self) -> List[Snapshot]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM snapshots ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_snapshot(row) for row in rows]

    # ------------------------------------------------------------------
    # Tile operations
    # ------------------------------------------------------------------
    def put_tiles(self, records: Iterable[TileIngestRecord]) -> List[TileMeta]:
        entries = list(records)
        if not entries:
            return []

        missing = [
            snapshot_id
            for snapshot_id in {entry.snapshot_id for entry in entries}
            if not self._snapshot_exists(snapshot_id)
        ]
        if missing:
            raise ValueError(f"Unknown snapshot IDs for tile ingest: {', '.join(sorted(missing))}")

        decoded: List[Tuple[TileMeta, bytes]] = []
        for record in entries:
            payload_bytes = self._decode_payload(record)
            tile_id = self._compute_tile_id(
                stream=record.stream,
                snapshot_id=record.snapshot_id,
                level=record.level,
                x=record.x,
                y=record.y,
                payload_bytes=payload_bytes,
            )
            checksum = blake3(payload_bytes).hexdigest()
            size_bytes = len(payload_bytes)
            tile_meta = TileMeta(
                tile_id=tile_id,
                stream=record.stream,
                snapshot_id=record.snapshot_id,
                level=record.level,
                x=record.x,
                y=record.y,
                shape=tuple(record.shape),
                dtype=record.dtype,
                parent_tile_id=record.parent_tile_id,
                halo=record.halo,
                checksum=checksum,
                size_bytes=size_bytes,
            )
            decoded.append((tile_meta, payload_bytes))

        existing = self._fetch_existing_tiles(tile_meta.tile_id for tile_meta, _ in decoded)

        stored: List[TileMeta] = []
        batch: List[Tuple] = []
        created_at = self._utcnow().isoformat()
        for tile_meta, payload_bytes in decoded:
            payload_path = self._tile_payload_path(tile_meta)
            payload_path.parent.mkdir(parents=True, exist_ok=True)
            current_meta = existing.get(tile_meta.tile_id)
            # Reuse the existing payload when the tile already lives on disk.
            if current_meta is None or not payload_path.exists():
                payload_path.write_bytes(payload_bytes)
            result_meta = tile_meta if current_meta is None or current_meta != tile_meta else current_meta
            stored.append(result_meta)
            existing[tile_meta.tile_id] = result_meta
            if current_meta is not None and current_meta == tile_meta:
                # Nothing to update for identical metadata.
                continue
            batch.append(
                (
                    tile_meta.tile_id,
                    tile_meta.stream,
                    tile_meta.snapshot_id,
                    tile_meta.level,
                    tile_meta.x,
                    tile_meta.y,
                    json.dumps(tile_meta.shape),
                    tile_meta.dtype,
                    tile_meta.parent_tile_id,
                    tile_meta.halo,
                    tile_meta.checksum,
                    tile_meta.size_bytes,
                    created_at,
                )
            )
        if not batch:
            return stored
        with self._lock:
            self._conn.executemany(
                """
                INSERT INTO tiles (
                    tile_id, stream, snapshot_id, level, x, y, shape, dtype,
                    parent_tile_id, halo, checksum, size_bytes, created_at,
                    access_count, last_access
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL)
                ON CONFLICT(tile_id) DO UPDATE SET
                    stream = excluded.stream,
                    snapshot_id = excluded.snapshot_id,
                    level = excluded.level,
                    x = excluded.x,
                    y = excluded.y,
                    shape = excluded.shape,
                    dtype = excluded.dtype,
                    parent_tile_id = excluded.parent_tile_id,
                    halo = excluded.halo,
                    checksum = excluded.checksum,
                    size_bytes = excluded.size_bytes,
                    created_at = excluded.created_at
                """,
                batch,
            )
            self._conn.commit()
        return stored

    def get_tile(self, tile_id: str) -> StoredTile:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM tiles WHERE tile_id = ?",
                (tile_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Tile '{tile_id}' not found")
        meta = self._row_to_tile_meta(row)
        payload_path = self._tile_payload_path(meta)
        if not payload_path.exists():
            raise FileNotFoundError(f"Payload for tile '{tile_id}' is missing at {payload_path}")
        self._register_access(tile_id)
        return StoredTile(metadata=meta, payload_path=payload_path)

    def get_tile_by_coordinate(
        self,
        *,
        stream: str,
        snapshot_id: str,
        level: int,
        x: int,
        y: int,
    ) -> StoredTile:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT * FROM tiles
                WHERE stream = ? AND snapshot_id = ? AND level = ? AND x = ? AND y = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (stream, snapshot_id, level, x, y),
            ).fetchone()
        if row is None:
            raise KeyError(
                "Tile not found for stream=%s snapshot=%s level=%d x=%d y=%d"
                % (stream, snapshot_id, level, x, y)
            )
        meta = self._row_to_tile_meta(row)
        payload_path = self._tile_payload_path(meta)
        if not payload_path.exists():
            raise FileNotFoundError(
                f"Payload for tile '{meta.tile_id}' is missing at {payload_path}"
            )
        self._register_access(meta.tile_id)
        return StoredTile(metadata=meta, payload_path=payload_path)

    def tiles_for_snapshot(
        self,
        snapshot_id: str,
        *,
        stream: Optional[str] = None,
        level_range: Optional[Tuple[int, int]] = None,
        bboxes: Optional[Sequence[Tuple[int, int, int, int]]] = None,
    ) -> List[TileMeta]:
        query = ["SELECT * FROM tiles WHERE snapshot_id = ?"]
        params: List[object] = [snapshot_id]
        if stream is not None:
            query.append("AND stream = ?")
            params.append(stream)
        if level_range is not None:
            max_level, min_level = level_range
            query.append("AND level BETWEEN ? AND ?")
            params.extend([min_level, max_level])
        if bboxes:
            clause, bbox_params = self._bbox_sql_clause(bboxes)
            if clause:
                query.append("AND")
                query.append(clause)
                params.extend(bbox_params)
        query.append("ORDER BY level ASC, created_at DESC, tile_id ASC")
        sql = " ".join(query)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        metas = [self._row_to_tile_meta(row) for row in rows]
        if not bboxes:
            return metas
        return [meta for meta in metas if self._tile_intersects_any(meta, bboxes)]

    # ------------------------------------------------------------------
    # Hint logging & introspection
    # ------------------------------------------------------------------
    def log_hints(self, hints: Iterable[QueryHint]) -> None:
        payload = list(hints)
        if not payload:
            return
        created_at = self._utcnow().isoformat()
        batch = []
        for hint in payload:
            level_max, level_min = hint.level_range
            batch.append(
                (
                    hint.query_id,
                    hint.snapshot_id,
                    hint.stream,
                    level_max,
                    level_min,
                    json.dumps(hint.bboxes),
                    hint.confidence,
                    created_at,
                )
            )
        with self._lock:
            self._conn.executemany(
                """
                INSERT INTO hints (
                    query_id, snapshot_id, stream, level_max, level_min,
                    bboxes, confidence, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                batch,
            )
            self._conn.commit()

    def iter_hints(self) -> Iterable[QueryHint]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM hints ORDER BY id ASC"
            ).fetchall()
        return tuple(self._row_to_hint(row) for row in rows)

    def recent_hints(
        self,
        snapshot_id: str,
        *,
        stream: Optional[str] = None,
        limit: int = 50,
        level_range: Optional[Tuple[int, int]] = None,
    ) -> List[QueryHint]:
        query = ["SELECT * FROM hints WHERE snapshot_id = ?"]
        params: List[object] = [snapshot_id]
        if stream is not None:
            query.append("AND stream = ?")
            params.append(stream)
        if level_range is not None:
            max_level, min_level = level_range
            query.append("AND level_max >= ? AND level_min <= ?")
            params.extend([min_level, max_level])
        query.append("ORDER BY created_at DESC, id DESC LIMIT ?")
        params.append(limit)
        sql = " ".join(query)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_hint(row) for row in rows]

    # ------------------------------------------------------------------
    # Tile statistics
    # ------------------------------------------------------------------
    def tile_usage_for_snapshot(self, snapshot_id: str) -> Dict[str, TileUsage]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT tile_id, access_count, last_access FROM tiles WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchall()
        return {
            row["tile_id"]: TileUsage(
                access_count=row["access_count"],
                last_access=(
                    datetime.fromisoformat(row["last_access"]) if row["last_access"] else None
                ),
            )
            for row in rows
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                PRAGMA journal_mode = WAL;
                PRAGMA synchronous = NORMAL;
                PRAGMA temp_store = MEMORY;
                PRAGMA cache_size = -100000;
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    parents TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    provenance TEXT NOT NULL,
                    merge_policy TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tiles (
                    tile_id TEXT PRIMARY KEY,
                    stream TEXT NOT NULL,
                    snapshot_id TEXT NOT NULL,
                    level INTEGER NOT NULL,
                    x INTEGER NOT NULL,
                    y INTEGER NOT NULL,
                    shape TEXT NOT NULL,
                    dtype TEXT NOT NULL,
                    parent_tile_id TEXT,
                    halo INTEGER,
                    checksum TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    access_count INTEGER NOT NULL DEFAULT 0,
                    last_access TEXT,
                    FOREIGN KEY(snapshot_id) REFERENCES snapshots(snapshot_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_tiles_snapshot_level
                    ON tiles(snapshot_id, level);
                CREATE INDEX IF NOT EXISTS idx_tiles_coords
                    ON tiles(snapshot_id, stream, level, x, y);

                CREATE TABLE IF NOT EXISTS hints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_id TEXT NOT NULL,
                    snapshot_id TEXT NOT NULL,
                    stream TEXT NOT NULL,
                    level_max INTEGER NOT NULL,
                    level_min INTEGER NOT NULL,
                    bboxes TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_hints_snapshot
                    ON hints(snapshot_id, created_at DESC);
                """
            )
            self._conn.commit()

    def _snapshot_exists(self, snapshot_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM snapshots WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchone()
        return row is not None

    def snapshot_exists(self, snapshot_id: str) -> bool:
        """Return True when the snapshot is present in the catalog."""

        return self._snapshot_exists(snapshot_id)

    def _register_access(self, tile_id: str) -> None:
        timestamp = self._utcnow().isoformat()
        with self._lock:
            self._conn.execute(
                """
                UPDATE tiles
                SET access_count = access_count + 1, last_access = ?
                WHERE tile_id = ?
                """,
                (timestamp, tile_id),
            )
            self._conn.commit()

    def _decode_payload(self, record: TileIngestRecord) -> bytes:
        from base64 import b64decode

        return b64decode(record.payload.bytes_b64)

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)

    def _row_to_snapshot(self, row: sqlite3.Row) -> Snapshot:
        return Snapshot.model_validate(
            {
                "snapshot_id": row["snapshot_id"],
                "parents": json.loads(row["parents"]),
                "created_at": datetime.fromisoformat(row["created_at"]),
                "tags": json.loads(row["tags"]),
                "provenance": json.loads(row["provenance"]),
                "merge_policy": row["merge_policy"],
            }
        )

    def _row_to_tile_meta(self, row: sqlite3.Row) -> TileMeta:
        return TileMeta.model_validate(
            {
                "tile_id": row["tile_id"],
                "stream": row["stream"],
                "snapshot_id": row["snapshot_id"],
                "level": row["level"],
                "x": row["x"],
                "y": row["y"],
                "shape": tuple(json.loads(row["shape"])),
                "dtype": row["dtype"],
                "parent_tile_id": row["parent_tile_id"],
                "halo": row["halo"],
                "checksum": row["checksum"],
                "size_bytes": row["size_bytes"],
            }
        )

    def _row_to_hint(self, row: sqlite3.Row) -> QueryHint:
        return QueryHint.model_validate(
            {
                "query_id": row["query_id"],
                "snapshot_id": row["snapshot_id"],
                "stream": row["stream"],
                "level_range": (row["level_max"], row["level_min"]),
                "bboxes": json.loads(row["bboxes"]),
                "confidence": row["confidence"],
            }
        )

    def _tile_payload_path(self, tile_meta: TileMeta) -> Path:
        prefix = tile_meta.tile_id[:12]
        return (
            self.root
            / "tiles"
            / tile_meta.stream
            / tile_meta.snapshot_id
            / f"L{tile_meta.level}"
            / f"x{tile_meta.x}"
            / f"y{tile_meta.y}"
            / f"{prefix}.bin"
        )

    @staticmethod
    def _tile_intersects_any(
        meta: TileMeta, bboxes: Sequence[Tuple[int, int, int, int]]
    ) -> bool:
        for bbox in bboxes:
            x, y, w, h = bbox
            if meta.x >= x and meta.x < x + w and meta.y >= y and meta.y < y + h:
                return True
        return False

    def _bbox_sql_clause(
        self, bboxes: Sequence[Tuple[int, int, int, int]]
    ) -> Tuple[str, List[int]]:
        seen = set()
        params: List[int] = []
        clauses: List[str] = []
        for bbox in bboxes:
            if len(bbox) != 4:
                continue
            x, y, w, h = bbox
            if w <= 0 or h <= 0:
                continue
            x_max = x + w - 1
            y_max = y + h - 1
            key = (x, x_max, y, y_max)
            if key in seen:
                continue
            seen.add(key)
            clauses.append("(x BETWEEN ? AND ? AND y BETWEEN ? AND ?)")
            params.extend([x, x_max, y, y_max])
        if not clauses:
            return "", []
        return f"({' OR '.join(clauses)})", params

    def _fetch_existing_tiles(
        self, tile_ids: Iterable[str]
    ) -> Dict[str, TileMeta]:
        identifiers = tuple(dict.fromkeys(tile_ids))
        if not identifiers:
            return {}
        placeholders = ",".join("?" for _ in identifiers)
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM tiles WHERE tile_id IN ({placeholders})",
                identifiers,
            ).fetchall()
        return {row["tile_id"]: self._row_to_tile_meta(row) for row in rows}

    def _compute_tile_id(
        self,
        *,
        stream: str,
        snapshot_id: str,
        level: int,
        x: int,
        y: int,
        payload_bytes: bytes,
    ) -> str:
        digest = blake3()
        for part in (stream, snapshot_id, str(level), str(x), str(y)):
            digest.update(part.encode("utf-8"))
        digest.update(payload_bytes)
        return digest.hexdigest()


__all__ = ["HierarchicalImageMemory", "StoredTile", "TileUsage"]
