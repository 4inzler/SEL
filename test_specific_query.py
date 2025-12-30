"""Test retrieval with a specific topic from past conversations."""

import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent / "project_echo"))

from sel_bot.memory import MemoryManager

# Initialize memory manager
him_root = Path("sel_data/him_store")
memory_manager = MemoryManager(
    state_manager=None,
    him_root=him_root,
    max_level=3,
)

# Test with a specific topic from the conversation history I saw
queries = [
    "favorite color",
    "alive feeling",
    "veci fellows working faster",
]

for query in queries:
    print(f"\n{'='*80}")
    print(f"Query: '{query}'")
    print('='*80)

    memories = memory_manager._retrieve_sync("1416008355163406367", query, limit=5)

    if memories:
        now = datetime.now(timezone.utc)
        for i, mem in enumerate(memories, 1):
            age_days = (now - mem.timestamp).days if mem.timestamp else 0
            print(f"\n{i}. [{age_days} days old]")
            print(f"   {mem.summary[:100]}...")
    else:
        print("No memories found")
