"""Move backfilled database to where the bot is looking."""

from pathlib import Path
import shutil

src = Path("project_echo/sel_data/him_store")
dst = Path("project_echo/data/him_store")
backup = Path("project_echo/data/him_store.backup")

print(f"Source: {src}")
print(f"Destination: {dst}")

# Backup existing database
if dst.exists():
    if backup.exists():
        shutil.rmtree(backup)
    shutil.move(str(dst), str(backup))
    print(f"[OK] Backed up existing database to {backup}")

# Copy backfilled database
shutil.copytree(str(src), str(dst))
print(f"[OK] Copied backfilled database to {dst}")

# Verify
tile_count = len(list((dst / "tiles").rglob("*.bin")))
print(f"[OK] New tile count: {tile_count}")

# Check database
import sqlite3
db_path = dst / "him.db"
if db_path.exists():
    conn = sqlite3.connect(db_path)
    snapshots = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
    tiles = conn.execute("SELECT COUNT(*) FROM tiles WHERE level=0").fetchone()[0]
    conn.close()
    print(f"[OK] Database contains: {snapshots} snapshots, {tiles} L0 tiles")
