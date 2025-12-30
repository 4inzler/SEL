"""
Clean HIM-backed memories by removing duplicates, empty entries, and optionally trimming
older items for selected channels.

Usage:
    poetry run python -m tools.clean_memories --channel chan_id [--max-age-hours 720] [--dry-run]

Arguments:
    --channel / -c     Channel ID to clean. Repeatable; if omitted, all snapshots are processed.
    --max-age-hours    Drop memories older than this many hours (optional).
    --dry-run          Show what would be removed without modifying storage.
    --limit            Max memories to inspect per channel (default 5000).
    --him-root         HIM storage directory (defaults to Settings.him_memory_dir or env HIM_MEMORY_DIR).
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import logging
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from him.storage import HierarchicalImageMemory


logger = logging.getLogger("clean_memories")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean HIM memories.")
    parser.add_argument("-c", "--channel", action="append", help="Channel ID to clean (repeatable)")
    parser.add_argument("--max-age-hours", type=float, default=None, help="Drop memories older than this many hours")
    parser.add_argument("--dry-run", action="store_true", help="Show deletions without applying")
    parser.add_argument("--limit", type=int, default=5000, help="Max memories to inspect per channel")
    parser.add_argument(
        "--him-root",
        type=Path,
        default=None,
        help="HIM storage directory (defaults to env HIM_MEMORY_DIR or ./sel_data/him_store)",
    )
    return parser.parse_args()


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iter_memories(store: HierarchicalImageMemory, snapshot_id: str, limit: int) -> Iterable[Tuple[str, Path]]:
    # Walk tiles for episodic memories (vector/json;memory_v3)
    metas = store.tiles_for_snapshot(snapshot_id, stream="episodic_vector", level_range=(10, 0))
    count = 0
    for meta in metas:
        if count >= limit:
            break
        payload_path = store._tile_payload_path(meta)  # type: ignore[attr-defined]
        if payload_path.exists():
            yield meta.tile_id, payload_path
            count += 1


def _decode_payload(path: Path) -> Optional[dict]:
    try:
        raw = path.read_bytes()
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def clean_channel(
    store: HierarchicalImageMemory,
    snapshot_id: str,
    *,
    max_age_hours: Optional[float],
    limit: int,
    dry_run: bool,
) -> Tuple[int, int]:
    now = _now()
    seen: set[str] = set()
    removed = 0
    kept = 0
    for tile_id, payload_path in _iter_memories(store, snapshot_id, limit):
        payload = _decode_payload(payload_path)
        if not payload:
            if not dry_run:
                payload_path.unlink(missing_ok=True)
            removed += 1
            continue

        summary = str(payload.get("summary") or "").strip()
        if not summary:
            if not dry_run:
                payload_path.unlink(missing_ok=True)
            removed += 1
            continue

        ts_raw = payload.get("timestamp")
        if max_age_hours is not None and ts_raw:
            try:
                ts = dt.datetime.fromisoformat(ts_raw)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=dt.timezone.utc)
                age_hours = (now - ts).total_seconds() / 3600.0
                if age_hours > max_age_hours:
                    if not dry_run:
                        payload_path.unlink(missing_ok=True)
                    removed += 1
                    continue
            except Exception:
                pass

        key = summary.lower()
        if key in seen:
            if not dry_run:
                payload_path.unlink(missing_ok=True)
            removed += 1
            continue
        seen.add(key)
        kept += 1
    return kept, removed


async def main() -> None:
    args = parse_args()
    him_root = args.him_root or Path(
        os.getenv("HIM_MEMORY_DIR") or Path("sel_data") / "him_store"  # type: ignore[name-defined]
    )
    store = HierarchicalImageMemory(him_root)

    snapshots = store.list_snapshots()
    targets = [s.snapshot_id for s in snapshots] if not args.channel else [str(c) for c in args.channel]
    for snapshot_id in targets:
        kept, removed = clean_channel(
            store,
            snapshot_id,
            max_age_hours=args.max_age_hours,
            limit=args.limit,
            dry_run=args.dry_run,
        )
        logger.info(
            "Channel %s cleaned: kept=%s removed=%s%s",
            snapshot_id,
            kept,
            removed,
            " (dry-run)" if args.dry_run else "",
        )


if __name__ == "__main__":
    import os  # local import to avoid global dependency in tool

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    asyncio.run(main())
