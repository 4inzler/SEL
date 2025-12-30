import json

import pytest

from him import (
    HierarchicalImageMemory,
    SnapshotCreate,
    SnapshotProvenance,
    scene_to_tiles,
    svg_to_scene,
)


def _create_snapshot(store: HierarchicalImageMemory, snapshot_id: str) -> None:
    payload = SnapshotCreate(
        snapshot_id=snapshot_id,
        parents=[],
        tags={"test": "vector"},
        provenance=SnapshotProvenance(
            model="test",
            code_sha="test",
        ),
    )
    store.create_snapshot(payload)


def test_svg_to_scene_parses_primitives() -> None:
    svg = """
    <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
        <rect x="10" y="10" width="80" height="20" fill="#ff0000" />
        <circle cx="50" cy="60" r="10" stroke="#00ff00" />
    </svg>
    """
    scene = svg_to_scene(svg)
    assert len(scene.shapes) == 2
    rect, circle = scene.shapes
    assert rect.kind == "rect"
    assert circle.kind == "circle"
    # Rect normalised coordinates should span most of the width.
    min_x, _, max_x, _ = rect.bounding_box()
    assert pytest.approx(min_x, rel=1e-6) == 0.1
    assert pytest.approx(max_x, rel=1e-6) == 0.9


def test_scene_to_tiles_ingests_into_store(tmp_path) -> None:
    svg = """
    <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="0" width="100" height="100" fill="#112233" />
        <line x1="0" y1="0" x2="100" y2="100" stroke="#ffffff" />
    </svg>
    """
    store = HierarchicalImageMemory(tmp_path)
    snapshot_id = "vector-snapshot"
    _create_snapshot(store, snapshot_id)

    scene = svg_to_scene(svg)
    records = scene_to_tiles(scene, snapshot_id=snapshot_id, max_level=2)
    metas = store.put_tiles(records)

    assert metas
    # Level 0 tile should exist and contain both primitives.
    tile = store.get_tile_by_coordinate(
        stream="vector_scene",
        snapshot_id=snapshot_id,
        level=0,
        x=0,
        y=0,
    )
    payload = json.loads(tile.payload_path.read_bytes().decode("utf-8"))
    assert payload["level"] == 0
    kinds = {shape["kind"] for shape in payload["shapes"]}
    assert kinds == {"rect", "line"}
    # Ensure deeper levels are generated.
    levels = {meta.level for meta in metas}
    assert levels == {0, 1, 2}
