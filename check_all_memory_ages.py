"""Check the age distribution of all memories in the main channel."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter

# Connect to HIM database (use the one bot is actually reading from)
him_dir = Path("project_echo/data/him_store")
db_path = him_dir / "him.db"

conn = sqlite3.connect(db_path)

# Get all L0 tiles for the main channel
channel_id = "1416008355163406367"
tiles = conn.execute(
    'SELECT tile_id, stream, snapshot_id, level, x, y FROM tiles WHERE snapshot_id=? AND level=0',
    (channel_id,)
).fetchall()

print(f"Analyzing {len(tiles)} L0 tiles from channel {channel_id}\n")

now = datetime.now(timezone.utc)
age_buckets = Counter()
errors = 0

for tile_id, stream, snapshot_id, level, x, y in tiles:
    # Construct payload path
    tile_id_prefix = tile_id[:12]
    payload_path = f"tiles/{stream}/{snapshot_id}/L{level}/x{x}/y{y}/{tile_id_prefix}.bin"
    payload_file = him_dir / payload_path

    if not payload_file.exists():
        errors += 1
        continue

    try:
        payload_json = json.loads(payload_file.read_bytes())
        payload_timestamp_str = payload_json.get("timestamp")

        if payload_timestamp_str:
            payload_timestamp = datetime.fromisoformat(payload_timestamp_str)
            age = now - payload_timestamp
            age_days = age.days

            # Bucket by age
            if age_days == 0:
                age_buckets["Today (0 days)"] += 1
            elif age_days <= 7:
                age_buckets["Last week (1-7 days)"] += 1
            elif age_days <= 30:
                age_buckets["Last month (8-30 days)"] += 1
            elif age_days <= 60:
                age_buckets["Last 2 months (31-60 days)"] += 1
            else:
                age_buckets[f"Older than 60 days"] += 1
    except Exception as e:
        errors += 1

print("Age Distribution:")
for bucket in ["Today (0 days)", "Last week (1-7 days)", "Last month (8-30 days)",
               "Last 2 months (31-60 days)", "Older than 60 days"]:
    count = age_buckets.get(bucket, 0)
    percentage = (count / len(tiles) * 100) if tiles else 0
    print(f"  {bucket:30} {count:4} ({percentage:5.1f}%)")

if errors:
    print(f"\nErrors reading payloads: {errors}")

conn.close()
