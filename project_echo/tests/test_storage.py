from __future__ import annotations

import base64
from pathlib import Path

from him.models import (
    QueryHint,
    SnapshotCreate,
    SnapshotProvenance,
    TileIngestRecord,
    TilePayload,
)
from him.storage import HierarchicalImageMemory


def sample_payload(data: bytes) -> str:
    return base64.b64encode(data).decode("utf-8")


def create_snapshot(store: HierarchicalImageMemory, snapshot_id: str) -> None:
    store.create_snapshot(
        SnapshotCreate(
            snapshot_id=snapshot_id,
            parents=[],
            tags={"task_id": "T1"},
            provenance=SnapshotProvenance(model="test", code_sha="deadbeef"),
        )
    )


def test_create_snapshot_and_put_tile(tmp_path: Path) -> None:
    store = HierarchicalImageMemory(tmp_path)
    create_snapshot(store, "snp_test")

    tile = TileIngestRecord(
        stream="kv_cache",
        snapshot_id="snp_test",
        level=0,
        x=0,
        y=0,
        shape=(512, 512, 1),
        dtype="fp16",
        payload=TilePayload(bytes_b64=sample_payload(b"tile-bytes")),
    )
    stored = store.put_tiles([tile])
    assert stored and stored[0].tile_id

    retrieved = store.get_tile(stored[0].tile_id)
    assert retrieved.payload_path.read_bytes() == b"tile-bytes"

    usage = store.tile_usage_for_snapshot("snp_test")
    assert usage[stored[0].tile_id].access_count == 1

    located = store.get_tile_by_coordinate(
        stream="kv_cache",
        snapshot_id="snp_test",
        level=0,
        x=0,
        y=0,
    )
    assert located.metadata.tile_id == stored[0].tile_id

    usage = store.tile_usage_for_snapshot("snp_test")
    assert usage[stored[0].tile_id].access_count == 2


def test_tiles_for_snapshot_filters(tmp_path: Path) -> None:
    store = HierarchicalImageMemory(tmp_path)
    create_snapshot(store, "snp_levels")

    tiles = [
        TileIngestRecord(
            stream="kv_cache",
            snapshot_id="snp_levels",
            level=level,
            x=idx,
            y=idx,
            shape=(512, 512, 1),
            dtype="fp16",
            payload=TilePayload(bytes_b64=sample_payload(f"tile-{level}".encode("utf-8"))),
        )
        for idx, level in enumerate((0, 1, 2))
    ]
    store.put_tiles(tiles)

    filtered = store.tiles_for_snapshot("snp_levels", level_range=(1, 1))
    assert len(filtered) == 1
    assert filtered[0].level == 1


def test_tiles_for_snapshot_bbox_sql(tmp_path: Path) -> None:
    store = HierarchicalImageMemory(tmp_path)
    create_snapshot(store, "snp_bbox")

    tiles = [
        TileIngestRecord(
            stream="kv_cache",
            snapshot_id="snp_bbox",
            level=0,
            x=idx,
            y=idx,
            shape=(512, 512, 1),
            dtype="fp16",
            payload=TilePayload(bytes_b64=sample_payload(f"bbox-{idx}".encode("utf-8"))),
        )
        for idx in range(3)
    ]
    store.put_tiles(tiles)

    filtered = store.tiles_for_snapshot(
        "snp_bbox",
        bboxes=[(1, 1, 1, 1)],
        level_range=(2, 0),
    )
    assert len(filtered) == 1
    assert filtered[0].x == 1 and filtered[0].y == 1


def test_put_tiles_skips_duplicate_writes(tmp_path: Path) -> None:
    store = HierarchicalImageMemory(tmp_path)
    create_snapshot(store, "snp_dedupe")

    tile = TileIngestRecord(
        stream="kv_cache",
        snapshot_id="snp_dedupe",
        level=0,
        x=0,
        y=0,
        shape=(512, 512, 1),
        dtype="fp16",
        payload=TilePayload(bytes_b64=sample_payload(b"dedupe")),
    )

    first_meta = store.put_tiles([tile])[0]
    payload_path = store.get_tile(first_meta.tile_id).payload_path
    first_mtime = payload_path.stat().st_mtime_ns

    second_meta = store.put_tiles([tile])[0]
    assert second_meta.tile_id == first_meta.tile_id
    assert payload_path.stat().st_mtime_ns == first_mtime


def test_hint_logging(tmp_path: Path) -> None:
    store = HierarchicalImageMemory(tmp_path)
    create_snapshot(store, "snp_hints")

    hint = QueryHint(
        query_id="q1",
        snapshot_id="snp_hints",
        stream="kv_cache",
        level_range=(2, 0),
        bboxes=[(0, 0, 4, 4)],
        confidence=0.9,
    )
    store.log_hints([hint])

    recorded = list(store.iter_hints())
    assert recorded and recorded[0].query_id == "q1"

    recent = store.recent_hints("snp_hints", stream="kv_cache")
    assert recent and recent[0].snapshot_id == "snp_hints"
