"""CLI entry point for vector-based image ingestion."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from ..models import SnapshotCreate, SnapshotProvenance
from ..storage import HierarchicalImageMemory
from ..vector import load_svg_scene, scene_to_tiles


def _ensure_snapshot(store: HierarchicalImageMemory, snapshot_id: str) -> None:
    try:
        store.get_snapshot(snapshot_id)
    except KeyError:
        payload = SnapshotCreate(
            snapshot_id=snapshot_id,
            parents=[],
            tags={"source": "vector_ingest"},
            provenance=SnapshotProvenance(
                model="vector-ingest",
                code_sha="vector-ingest",
                seed=int(datetime.now(tz=timezone.utc).timestamp()),
            ),
        )
        store.create_snapshot(payload)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest a vector image into the HIM store")
    parser.add_argument("svg", help="Path to the SVG document to ingest")
    parser.add_argument("snapshot_id", help="Snapshot identifier that will receive the tiles")
    parser.add_argument("--data-dir", default="data", help="Storage directory for the HIM database")
    parser.add_argument("--stream", default="vector_scene", help="Target stream name")
    parser.add_argument("--max-level", type=int, default=4, help="Maximum pyramid level to materialise")
    args = parser.parse_args()

    store = HierarchicalImageMemory(args.data_dir)
    _ensure_snapshot(store, args.snapshot_id)

    scene = load_svg_scene(args.svg)
    records = scene_to_tiles(scene, snapshot_id=args.snapshot_id, stream=args.stream, max_level=args.max_level)
    metas = store.put_tiles(records)
    summary = {
        "snapshot_id": args.snapshot_id,
        "stream": args.stream,
        "tiles_ingested": len(metas),
        "levels": sorted({meta.level for meta in metas}),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
