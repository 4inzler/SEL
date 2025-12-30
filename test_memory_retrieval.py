"""Test memory retrieval to verify SEL can access historical memories."""

import sys
from pathlib import Path

# Add project_echo to path
sys.path.insert(0, str(Path(__file__).parent / "project_echo"))

from sel_bot.memory import MemoryManager

# Initialize memory manager with the configured path
# Since this runs from project_echo/, use relative path from there
him_root = Path("sel_data/him_store")
memory_manager = MemoryManager(
    state_manager=None,
    him_root=him_root,
    max_level=3,
)

# Test retrieval for the main channel
channel_id = "1416008355163406367"
query = "what do you remember about me?"

print(f"Testing memory retrieval from: {him_root}")
print(f"Channel: {channel_id}")
print(f"Query: {query}\n")

# Synchronous retrieval
memories = memory_manager._retrieve_sync(channel_id, query, limit=10)

print(f"Retrieved {len(memories)} memories:\n")
print("=" * 80)

for i, mem in enumerate(memories, 1):
    age_days = None
    if mem.timestamp:
        from datetime import datetime, timezone
        age = datetime.now(timezone.utc) - mem.timestamp
        age_days = age.days

    print(f"\n{i}. [{age_days} days old]")
    print(f"   Summary: {mem.summary[:100]}...")
    print(f"   Salience: {mem.salience:.2f}")
    print(f"   Tags: {', '.join(mem.tags)}")

print("\n" + "=" * 80)
print(f"\nSummary:")
print(f"  - Total memories retrieved: {len(memories)}")
if memories:
    ages = [age for mem in memories if mem.timestamp for age in [(datetime.now(timezone.utc) - mem.timestamp).days]]
    if ages:
        print(f"  - Oldest memory: {max(ages)} days ago")
        print(f"  - Newest memory: {min(ages)} days ago")
        print(f"  - Average age: {sum(ages) // len(ages)} days")
