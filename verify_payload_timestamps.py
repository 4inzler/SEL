"""Verify that backfilled memories have correct timestamps in their payloads."""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

# Connect to HIM database
him_dir = Path("project_echo/sel_data/him_store")
db_path = him_dir / "him.db"

if not db_path.exists():
    print(f"Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)

# Get tiles for the main channel
channel_id = "1416008355163406367"
tiles = conn.execute(
    'SELECT tile_id, stream, snapshot_id, level, x, y, created_at FROM tiles WHERE snapshot_id=? AND level=0 ORDER BY created_at LIMIT 20',
    (channel_id,)
).fetchall()

print(f"\nChecking {len(tiles)} tiles from channel {channel_id}:\n")

now = datetime.now()
recent_count = 0
old_week_count = 0
old_month_count = 0

for tile_id, stream, snapshot_id, level, x, y, db_created_at in tiles:
    # Construct payload path: tiles/{stream}/{snapshot_id}/L{level}/x{x}/y{y}/{tile_id[:12]}.bin
    tile_id_prefix = tile_id[:12]
    payload_path = f"tiles/{stream}/{snapshot_id}/L{level}/x{x}/y{y}/{tile_id_prefix}.bin"
    payload_file = him_dir / payload_path
    if not payload_file.exists():
        print(f"Payload file missing: {payload_path}")
        continue

    try:
        payload_json = json.loads(payload_file.read_bytes())
        payload_timestamp_str = payload_json.get("timestamp")
        summary = payload_json.get("summary", "")[:80]

        if payload_timestamp_str:
            payload_timestamp = datetime.fromisoformat(payload_timestamp_str)
            age = now - payload_timestamp.replace(tzinfo=None)

            # Count by age
            if age < timedelta(hours=2):
                recent_count += 1
            if age > timedelta(days=7):
                old_week_count += 1
            if age > timedelta(days=30):
                old_month_count += 1

            print(f"Payload timestamp: {payload_timestamp_str}")
            print(f"DB created_at: {db_created_at}")
            print(f"Age: {age.days} days, {age.seconds // 3600} hours")
            print(f"Summary: {summary}")
            print("-" * 80)
    except Exception as e:
        print(f"Error reading payload {payload_path}: {e}")

print(f"\n=== Summary ===")
print(f"Total checked: {len(tiles)}")
print(f"Payload timestamps from last 2 hours: {recent_count}")
print(f"Payload timestamps older than 1 week: {old_week_count}")
print(f"Payload timestamps older than 1 month: {old_month_count}")

conn.close()
