from __future__ import annotations

import pytest

from sel_bot.memory import MemoryManager


@pytest.mark.asyncio
async def test_him_memory_store_and_recall(tmp_path) -> None:
    manager = MemoryManager(
        state_manager=None,
        him_root=tmp_path,
        max_level=2,
    )

    await manager.maybe_store("chan-1", "We talked about coffee brewing tips", tags=["chat"], salience=0.7)
    await manager.maybe_store("chan-1", "User shared a sleepy cat photo", tags=["user_message"], salience=0.9)

    memories = await manager.retrieve("chan-1", "coffee tips", limit=3)
    assert memories
    assert any("coffee" in mem.summary.lower() for mem in memories)

    tiles = manager.store.tiles_for_snapshot("chan-1", stream=manager.stream, level_range=(2, 0))
    assert len(tiles) >= 2
    assert all(tile.dtype.startswith("vector/json") for tile in tiles)
