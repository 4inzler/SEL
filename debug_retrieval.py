"""Debug memory retrieval to understand why memories aren't being found."""

import sys
from pathlib import Path

# Add project_echo to path
sys.path.insert(0, str(Path(__file__).parent / "project_echo"))

from sel_bot.memory import MemoryManager, generate_embedding

# Initialize memory manager with the configured path
him_root = Path("project_echo/sel_data/him_store")
memory_manager = MemoryManager(
    state_manager=None,
    him_root=him_root,
    max_level=3,
)

# Test channel
channel_id = "1416008355163406367"

print(f"HIM root: {him_root}")
print(f"Channel: {channel_id}\n")

# Check if snapshot exists
snapshot_exists = memory_manager.store.snapshot_exists(channel_id)
print(f"Snapshot exists: {snapshot_exists}")

if snapshot_exists:
    # Check tiles at each level
    for level in range(4):
        tiles = memory_manager.store.tiles_for_snapshot(
            channel_id,
            stream="episodic_vector",
            level_range=(level, level),
        )
        print(f"Level {level}: {len(tiles)} tiles")
        if tiles and level == 0:
            print(f"  First tile: {tiles[0].tile_id[:20]}... at ({tiles[0].x}, {tiles[0].y})")

    # Test query embedding and bbox
    query = "what do you remember?"
    query_vec = generate_embedding(query)
    print(f"\nQuery: {query}")
    print(f"Query vector (first 6): {query_vec[:6]}")

    from sel_bot.memory import _bbox_for_level
    for level in range(4):
        bbox = _bbox_for_level(query_vec, level, radius=1)
        print(f"Level {level} bbox: {bbox} (x0, y0, width, height)")
else:
    print("\n❌ Snapshot does not exist!")
    print("\nChecking what snapshots DO exist:")
    import sqlite3
    db_path = him_root / "him.db"
    if db_path.exists():
        conn = sqlite3.connect(db_path)
        snapshots = conn.execute("SELECT DISTINCT snapshot_id FROM snapshots").fetchall()
        print(f"Found {len(snapshots)} snapshots:")
        for (sid,) in snapshots[:10]:
            print(f"  - {sid}")
        conn.close()
