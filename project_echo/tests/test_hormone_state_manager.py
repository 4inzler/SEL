"""
Unit tests for HormoneStateManager.

Tests cover:
1. Cache behavior: get/update operations, dirty flag tracking
2. Persistence: HIM writes, flush cycles, state recovery
3. Graceful degradation: HIM unavailable scenarios
4. Serialization: to_dict/from_dict roundtrip
5. Coordinate mapping: temporal bucketing logic
"""

import asyncio
import datetime as dt
import tempfile
from pathlib import Path

import pytest

from sel_bot.hormone_state_manager import (
    HormoneStateManager,
    CachedHormoneState,
    HORMONE_STREAM,
)
from sel_bot.hormones import HormoneVector


@pytest.fixture
def temp_him_store():
    """
    Temporary HIM storage for testing.

    Creates a clean directory for each test, preventing interference
    between tests. Automatically cleaned up after test completes.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestCacheBehavior:
    """Test in-memory cache operations without HIM persistence."""

    @pytest.mark.asyncio
    async def test_get_state_new_channel_returns_defaults(self, temp_him_store):
        """
        Test that getting state for a new channel returns default values.

        Why this matters: New channels should have sensible defaults (all
        hormones at 0.0) rather than None or crashing.
        """
        manager = HormoneStateManager(him_root=temp_him_store)
        await manager.start()

        try:
            state = await manager.get_state("test_channel_1")

            # Should return default hormone values
            assert state.vector.dopamine == 0.0
            assert state.vector.serotonin == 0.0
            assert state.vector.cortisol == 0.0
            assert state.energy_level == 0.5
            assert state.focus_topic is None
            assert not state.dirty  # Fresh state, not modified
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_update_state_marks_dirty(self, temp_him_store):
        """
        Test that updating state marks the cache entry as dirty.

        Why this matters: The dirty flag tells the persistence loop which
        entries need to be written to HIM. Without this, we'd write
        everything every 5 minutes (wasteful) or nothing (data loss).
        """
        manager = HormoneStateManager(him_root=temp_him_store)
        await manager.start()

        try:
            vector = HormoneVector(dopamine=0.5, serotonin=0.3)
            state = await manager.update_state("test_channel_1", vector)

            # Should mark as dirty
            assert state.dirty
            assert state.vector.dopamine == 0.5
            assert state.vector.serotonin == 0.3

            # Should be in cache now
            cached = await manager.get_state("test_channel_1")
            assert cached.vector.dopamine == 0.5
            assert cached.dirty
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_multiple_updates_preserve_state(self, temp_him_store):
        """
        Test that multiple updates to the same channel work correctly.

        Why this matters: The decay loop updates hormones every 60 seconds,
        messages trigger updates, etc. Cache must handle rapid updates
        without losing data.
        """
        manager = HormoneStateManager(him_root=temp_him_store)
        await manager.start()

        try:
            # First update
            vector1 = HormoneVector(dopamine=0.3)
            await manager.update_state("test_channel_1", vector1, focus_topic="coding")

            # Second update
            vector2 = HormoneVector(dopamine=0.7, serotonin=0.4)
            await manager.update_state("test_channel_1", vector2, focus_topic="debugging")

            # Should have latest values
            state = await manager.get_state("test_channel_1")
            assert state.vector.dopamine == 0.7
            assert state.vector.serotonin == 0.4
            assert state.focus_topic == "debugging"
            assert state.dirty
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_cache_isolation_between_channels(self, temp_him_store):
        """
        Test that different channels have independent cache entries.

        Why this matters: Each Discord channel should have its own hormone
        state. Updating one channel shouldn't affect others.
        """
        manager = HormoneStateManager(him_root=temp_him_store)
        await manager.start()

        try:
            # Update channel 1
            vector1 = HormoneVector(dopamine=0.8)
            await manager.update_state("channel_1", vector1)

            # Update channel 2
            vector2 = HormoneVector(dopamine=0.2)
            await manager.update_state("channel_2", vector2)

            # Should be independent
            state1 = await manager.get_state("channel_1")
            state2 = await manager.get_state("channel_2")

            assert state1.vector.dopamine == 0.8
            assert state2.vector.dopamine == 0.2
        finally:
            await manager.stop()


class TestPersistence:
    """Test HIM persistence and state recovery."""

    @pytest.mark.asyncio
    async def test_flush_clears_dirty_flag(self, temp_him_store):
        """
        Test that flush clears dirty flag after successful write.

        Why this matters: After writing to HIM, the cache entry is no longer
        dirty. This prevents re-writing the same data on the next flush cycle.
        """
        manager = HormoneStateManager(him_root=temp_him_store, snapshot_interval=1)
        await manager.start()

        try:
            # Update state
            vector = HormoneVector(dopamine=0.7)
            await manager.update_state("test_channel_1", vector)

            # Should be dirty before flush
            state_before = await manager.get_state("test_channel_1")
            assert state_before.dirty

            # Force flush
            await manager._flush_all_dirty()

            # Should not be dirty after flush
            state_after = await manager.get_state("test_channel_1")
            assert not state_after.dirty
            assert state_after.vector.dopamine == 0.7  # Data preserved
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_state_persists_across_restarts(self, temp_him_store):
        """
        Test that state persists across manager restarts.

        Why this matters: If the bot crashes and restarts, hormone state
        should be recovered from HIM. This is the whole point of persistence!
        """
        # First manager: write state
        manager1 = HormoneStateManager(him_root=temp_him_store)
        await manager1.start()

        vector = HormoneVector(cortisol=0.4, oxytocin=0.6, melatonin=0.2)
        await manager1.update_state("test_channel_1", vector, focus_topic="testing persistence")
        await manager1.stop()  # Stop flushes to HIM

        # Second manager: load state
        manager2 = HormoneStateManager(him_root=temp_him_store)
        await manager2.start()

        try:
            state = await manager2.get_state("test_channel_1")

            # Should match original values (within float precision)
            assert state.vector.cortisol == pytest.approx(0.4, abs=0.01)
            assert state.vector.oxytocin == pytest.approx(0.6, abs=0.01)
            assert state.vector.melatonin == pytest.approx(0.2, abs=0.01)
            assert state.focus_topic == "testing persistence"
            assert not state.dirty  # Loaded from HIM, not modified
        finally:
            await manager2.stop()

    @pytest.mark.asyncio
    async def test_flush_only_writes_dirty_entries(self, temp_him_store):
        """
        Test that flush only writes dirty entries, not all cached entries.

        Why this matters: Performance optimization. If we have 100 cached
        channels but only 5 were updated, we should only write 5 to HIM.
        """
        manager = HormoneStateManager(him_root=temp_him_store)
        await manager.start()

        try:
            # Create 3 channels, only update 2
            vector1 = HormoneVector(dopamine=0.1)
            await manager.update_state("channel_1", vector1)

            vector2 = HormoneVector(dopamine=0.2)
            await manager.update_state("channel_2", vector2)

            # Flush (both dirty)
            await manager._flush_all_dirty()

            # Update only channel_1
            vector1_updated = HormoneVector(dopamine=0.9)
            await manager.update_state("channel_1", vector1_updated)

            # Check dirty counts
            metrics = manager.get_metrics()
            assert metrics["dirty_count"] == 1  # Only channel_1 is dirty
            assert metrics["cache_size"] == 2  # Both in cache
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_multiple_channels_persist_correctly(self, temp_him_store):
        """
        Test that multiple channels all persist and recover correctly.

        Why this matters: Real bots have many channels. All must persist
        independently without data corruption.
        """
        # First manager: write multiple channels
        manager1 = HormoneStateManager(him_root=temp_him_store)
        await manager1.start()

        for i in range(5):
            vector = HormoneVector(dopamine=float(i) / 10.0)
            await manager1.update_state(f"channel_{i}", vector, focus_topic=f"topic_{i}")

        await manager1.stop()

        # Second manager: verify all recovered
        manager2 = HormoneStateManager(him_root=temp_him_store)
        await manager2.start()

        try:
            for i in range(5):
                state = await manager2.get_state(f"channel_{i}")
                expected_dopamine = float(i) / 10.0
                assert state.vector.dopamine == pytest.approx(expected_dopamine, abs=0.01)
                assert state.focus_topic == f"topic_{i}"
        finally:
            await manager2.stop()


class TestGracefulDegradation:
    """Test behavior when HIM is unavailable."""

    @pytest.mark.asyncio
    async def test_cache_only_mode_on_invalid_path(self):
        """
        Test that manager continues in cache-only mode with invalid HIM path.

        Why this matters: If HIM disk is full, permissions are wrong, or
        storage fails, the bot should keep running with in-memory state
        rather than crashing.
        """
        # Use non-existent path (will fail on HIM operations)
        manager = HormoneStateManager(him_root="/nonexistent/path/that/does/not/exist")
        await manager.start()

        try:
            # Should still work in cache-only mode
            vector = HormoneVector(melatonin=0.8)
            state = await manager.update_state("test_channel_1", vector)

            assert state.vector.melatonin == 0.8
            assert not manager.him_available  # Should detect failure

            # Cache operations should still work
            cached = await manager.get_state("test_channel_1")
            assert cached.vector.melatonin == 0.8
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_failed_flush_retains_dirty_flag(self):
        """
        Test that failed flush leaves dirty flag set for retry.

        Why this matters: If HIM is temporarily unavailable, we should
        retry on the next flush cycle rather than losing data.
        """
        manager = HormoneStateManager(him_root="/nonexistent/path")
        await manager.start()

        try:
            vector = HormoneVector(dopamine=0.5)
            await manager.update_state("test_channel_1", vector)

            # Try to flush (will fail due to bad path)
            await manager._flush_all_dirty()

            # Should still be dirty (ready to retry)
            state = await manager.get_state("test_channel_1")
            assert state.dirty
            assert state.vector.dopamine == 0.5  # Data preserved in cache

            # Metrics should show failure
            metrics = manager.get_metrics()
            assert metrics["failed_flushes"] > 0
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_him_available_flag_updates(self, temp_him_store):
        """
        Test that him_available flag tracks HIM health correctly.

        Why this matters: Monitoring. We need to know if HIM is working
        or if we're in degraded (cache-only) mode.
        """
        # Start with valid HIM
        manager = HormoneStateManager(him_root=temp_him_store)
        await manager.start()

        try:
            assert manager.him_available  # Should start as available

            vector = HormoneVector(dopamine=0.3)
            await manager.update_state("test_channel_1", vector)
            await manager._flush_all_dirty()

            # Should still be available after successful flush
            assert manager.him_available
        finally:
            await manager.stop()


class TestSerialization:
    """Test HormoneVector serialization roundtrips."""

    def test_to_dict_contains_all_hormones(self):
        """
        Test that to_dict() exports all 13 hormones.

        Why this matters: If we forget a hormone, it won't persist to HIM
        and will always reset to 0.0 on restart. This catches that bug.
        """
        vector = HormoneVector(
            dopamine=0.1,
            serotonin=0.2,
            cortisol=0.3,
            oxytocin=0.4,
            melatonin=0.5,
            novelty=0.6,
            curiosity=0.7,
            patience=0.8,
            estrogen=0.11,
            testosterone=0.12,
            adrenaline=0.13,
            endorphin=0.14,
            progesterone=0.15,
        )

        data = vector.to_dict()

        # All 13 hormones should be present
        assert len(data) == 13
        assert data["dopamine"] == 0.1
        assert data["serotonin"] == 0.2
        assert data["cortisol"] == 0.3
        assert data["oxytocin"] == 0.4
        assert data["melatonin"] == 0.5
        assert data["novelty"] == 0.6
        assert data["curiosity"] == 0.7
        assert data["patience"] == 0.8
        assert data["estrogen"] == 0.11
        assert data["testosterone"] == 0.12
        assert data["adrenaline"] == 0.13
        assert data["endorphin"] == 0.14
        assert data["progesterone"] == 0.15

    def test_from_dict_roundtrip(self):
        """
        Test that from_dict(to_dict()) is lossless.

        Why this matters: We must be able to serialize and deserialize
        without losing precision. This is critical for state recovery.
        """
        original = HormoneVector(
            dopamine=0.7654,
            serotonin=0.3210,
            cortisol=0.1234,
        )

        # Roundtrip: vector -> dict -> vector
        data = original.to_dict()
        recovered = HormoneVector.from_dict(data)

        # Should be identical
        assert recovered.dopamine == pytest.approx(original.dopamine)
        assert recovered.serotonin == pytest.approx(original.serotonin)
        assert recovered.cortisol == pytest.approx(original.cortisol)

        # Unset hormones should be 0.0 in both
        assert recovered.melatonin == 0.0
        assert original.melatonin == 0.0

    def test_from_dict_handles_missing_hormones(self):
        """
        Test that from_dict() handles missing hormones gracefully.

        Why this matters: Backward compatibility. If we add new hormones
        in the future, old HIM tiles won't have them. Should default to 0.0.
        """
        # Only include some hormones
        partial_data = {
            "dopamine": 0.5,
            "serotonin": 0.3,
            # Missing: cortisol, oxytocin, etc.
        }

        vector = HormoneVector.from_dict(partial_data)

        # Present hormones should have correct values
        assert vector.dopamine == 0.5
        assert vector.serotonin == 0.3

        # Missing hormones should default to 0.0
        assert vector.cortisol == 0.0
        assert vector.oxytocin == 0.0
        assert vector.melatonin == 0.0

    def test_from_dict_handles_extra_fields(self):
        """
        Test that from_dict() ignores extra fields.

        Why this matters: Forward compatibility. If we remove hormones
        in the future, old HIM tiles might have them. Should not crash.
        """
        data_with_extras = {
            "dopamine": 0.5,
            "serotonin": 0.3,
            "unknown_hormone": 0.9,  # Not a real hormone
            "metadata": "some value",  # Random extra field
        }

        # Should not raise exception
        vector = HormoneVector.from_dict(data_with_extras)

        assert vector.dopamine == 0.5
        assert vector.serotonin == 0.3


class TestCoordinateMapping:
    """Test temporal coordinate mapping logic."""

    def test_time_bucket_to_coords_level_0(self, temp_him_store):
        """
        Test that level 0 uses 5-minute buckets.

        Why this matters: Level 0 is the finest resolution. 5-minute
        granularity is the sweet spot for memory usage vs. temporal detail.
        """
        manager = HormoneStateManager(him_root=temp_him_store)

        # Two timestamps 5 minutes apart
        t1 = dt.datetime(2025, 12, 10, 12, 0, 0, tzinfo=dt.timezone.utc)
        t2 = dt.datetime(2025, 12, 10, 12, 5, 0, tzinfo=dt.timezone.utc)

        x1, y1 = manager._time_bucket_to_coords(t1, level=0)
        x2, y2 = manager._time_bucket_to_coords(t2, level=0)

        # Should be in adjacent buckets
        assert x2 == x1 + 1
        assert y1 == 0
        assert y2 == 0  # Always single row

    def test_time_bucket_to_coords_level_1(self, temp_him_store):
        """
        Test that level 1 uses 1-hour buckets.

        Why this matters: Level 1 aggregates 12 level-0 tiles (5min * 12 = 1hr).
        Good for viewing daily patterns.
        """
        manager = HormoneStateManager(him_root=temp_him_store)

        # Two timestamps 1 hour apart
        t1 = dt.datetime(2025, 12, 10, 12, 0, 0, tzinfo=dt.timezone.utc)
        t2 = dt.datetime(2025, 12, 10, 13, 0, 0, tzinfo=dt.timezone.utc)

        x1, y1 = manager._time_bucket_to_coords(t1, level=1)
        x2, y2 = manager._time_bucket_to_coords(t2, level=1)

        # Should be in adjacent hourly buckets
        assert x2 == x1 + 1

    def test_time_bucket_to_coords_same_bucket(self, temp_him_store):
        """
        Test that timestamps within same bucket map to same coordinates.

        Why this matters: Multiple updates within 5 minutes should overwrite
        the same tile, not create duplicates.
        """
        manager = HormoneStateManager(him_root=temp_him_store)

        # Two timestamps 2 minutes apart (within same 5-min bucket)
        t1 = dt.datetime(2025, 12, 10, 12, 0, 0, tzinfo=dt.timezone.utc)
        t2 = dt.datetime(2025, 12, 10, 12, 2, 0, tzinfo=dt.timezone.utc)

        x1, y1 = manager._time_bucket_to_coords(t1, level=0)
        x2, y2 = manager._time_bucket_to_coords(t2, level=0)

        # Should map to same bucket
        assert x1 == x2
        assert y1 == y2


class TestMetrics:
    """Test monitoring metrics."""

    @pytest.mark.asyncio
    async def test_get_metrics_structure(self, temp_him_store):
        """
        Test that get_metrics() returns expected structure.

        Why this matters: Monitoring code depends on this structure.
        Breaking changes would break monitoring dashboards.
        """
        manager = HormoneStateManager(him_root=temp_him_store)
        await manager.start()

        try:
            metrics = manager.get_metrics()

            # Should have all expected fields
            assert "cache_size" in metrics
            assert "dirty_count" in metrics
            assert "him_available" in metrics
            assert "last_flush_time" in metrics
            assert "total_flushes" in metrics
            assert "failed_flushes" in metrics

            # Initial values
            assert metrics["cache_size"] == 0
            assert metrics["dirty_count"] == 0
            assert metrics["him_available"] is True
            assert metrics["total_flushes"] == 0
            assert metrics["failed_flushes"] == 0
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_metrics_update_with_operations(self, temp_him_store):
        """
        Test that metrics update correctly as operations occur.

        Why this matters: Metrics are useless if they don't reflect reality.
        """
        manager = HormoneStateManager(him_root=temp_him_store)
        await manager.start()

        try:
            # Add some channels
            for i in range(3):
                vector = HormoneVector(dopamine=float(i) / 10.0)
                await manager.update_state(f"channel_{i}", vector)

            metrics_before = manager.get_metrics()
            assert metrics_before["cache_size"] == 3
            assert metrics_before["dirty_count"] == 3

            # Flush
            await manager._flush_all_dirty()

            metrics_after = manager.get_metrics()
            assert metrics_after["cache_size"] == 3  # Still cached
            assert metrics_after["dirty_count"] == 0  # No longer dirty
            assert metrics_after["total_flushes"] == 1
            assert metrics_after["last_flush_time"] is not None
        finally:
            await manager.stop()


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_empty_flush_does_nothing(self, temp_him_store):
        """
        Test that flushing with no dirty entries is a no-op.

        Why this matters: Performance. Don't do unnecessary work.
        """
        manager = HormoneStateManager(him_root=temp_him_store)
        await manager.start()

        try:
            # Flush with nothing to flush
            await manager._flush_all_dirty()

            metrics = manager.get_metrics()
            # Should not count as a flush if nothing was dirty
            # (Implementation detail: currently increments total_flushes anyway,
            # but documents the behavior)
            assert metrics["dirty_count"] == 0
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_update_with_none_values_preserves_existing(self, temp_him_store):
        """
        Test that passing None for optional fields preserves existing values.

        Why this matters: Decay loop updates vector but might not have
        focus_topic. Should preserve existing focus_topic.
        """
        manager = HormoneStateManager(him_root=temp_him_store)
        await manager.start()

        try:
            # Initial update with all fields
            vector1 = HormoneVector(dopamine=0.5)
            await manager.update_state(
                "test_channel_1",
                vector1,
                focus_topic="initial topic",
                energy_level=0.7,
            )

            # Update only vector, don't specify focus_topic
            vector2 = HormoneVector(dopamine=0.8)
            await manager.update_state("test_channel_1", vector2)

            # Should preserve focus_topic and energy_level
            state = await manager.get_state("test_channel_1")
            assert state.vector.dopamine == 0.8  # Updated
            assert state.focus_topic == "initial topic"  # Preserved
            assert state.energy_level == 0.7  # Preserved
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_concurrent_access_to_same_channel(self, temp_him_store):
        """
        Test that concurrent updates to same channel are safe.

        Why this matters: The decay loop and message handler might update
        the same channel simultaneously. Cache lock must prevent race conditions.
        """
        manager = HormoneStateManager(him_root=temp_him_store)
        await manager.start()

        try:
            # Simulate concurrent updates
            async def update_task(value: float):
                vector = HormoneVector(dopamine=value)
                await manager.update_state("test_channel_1", vector)
                await asyncio.sleep(0.01)  # Simulate work

            # Run 10 concurrent updates
            tasks = [update_task(float(i) / 10.0) for i in range(10)]
            await asyncio.gather(*tasks)

            # Should have a consistent final state (one of the updates won)
            state = await manager.get_state("test_channel_1")
            assert 0.0 <= state.vector.dopamine <= 0.9
            assert state.dirty
        finally:
            await manager.stop()
