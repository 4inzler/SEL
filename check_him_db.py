"""Check what database the HIM store is actually using."""

import sys
from pathlib import Path

# Add project_echo to path
sys.path.insert(0, str(Path(__file__).parent / "project_echo"))

from sel_bot.memory import MemoryManager

# Initialize memory manager with the configured path
him_root = Path("project_echo/sel_data/him_store")
memory_manager = MemoryManager(
    state_manager=None,
    him_root=him_root,
    max_level=3,
)

print(f"Configured HIM root: {him_root}")
print(f"HIM root absolute: {him_root.absolute()}")
print(f"Store object: {memory_manager.store}")
print(f"Store root_dir: {memory_manager.store.root_dir}")
print(f"Store root_dir absolute: {memory_manager.store.root_dir.absolute()}")

# Check if database file exists
db_path = memory_manager.store.root_dir / "him.db"
print(f"\nDatabase path: {db_path}")
print(f"Database exists: {db_path.exists()}")

if db_path.exists():
    import sqlite3
    conn = sqlite3.connect(db_path)
    snapshots = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
    tiles = conn.execute("SELECT COUNT(*) FROM tiles").fetchone()[0]
    print(f"Snapshots in DB: {snapshots}")
    print(f"Tiles in DB: {tiles}")
    conn.close()
