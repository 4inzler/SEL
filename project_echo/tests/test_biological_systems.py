from __future__ import annotations

import datetime as dt

from sel_bot.biological_systems import BiologicalState, MenstrualCycleState, memory_affects_mood


def test_memory_affects_mood_positive() -> None:
    effects = memory_affects_mood("I love that day, it was amazing and fun")
    assert effects.get("serotonin", 0) > 0
    assert effects.get("dopamine", 0) > 0


def test_memory_affects_mood_negative() -> None:
    effects = memory_affects_mood("That was a sad and painful loss")
    assert effects.get("serotonin", 0) < 0
    assert effects.get("cortisol", 0) > 0


def test_biological_state_roundtrip_meta() -> None:
    state = BiologicalState()
    state.last_activity_ts = dt.datetime(2024, 1, 3, tzinfo=dt.timezone.utc)
    state.last_activity_channel_id = "chan-9"
    state.daily_cortisol_sum = 1.25
    state.daily_cortisol_samples = 5
    state.sleep_inactive_minutes = 42

    payload = state.to_dict()
    restored = BiologicalState.from_dict(payload)

    assert restored.last_activity_channel_id == "chan-9"
    assert restored.daily_cortisol_sum == 1.25
    assert restored.daily_cortisol_samples == 5
    assert restored.sleep_inactive_minutes == 42


def test_menstrual_cycle_profiles_switch_monthly(monkeypatch) -> None:
    state = MenstrualCycleState(
        cycle_start_date=dt.datetime(2026, 1, 5, tzinfo=dt.timezone.utc),
        cycle_length=28,
        active_profile="common_28",
        profile_month="2026-01",
    )

    january_now = dt.datetime(2026, 1, 20, tzinfo=dt.timezone.utc)
    february_now = dt.datetime(2026, 2, 2, tzinfo=dt.timezone.utc)

    class _JanDateTime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return january_now if tz is not None else january_now.replace(tzinfo=None)

    monkeypatch.setattr("sel_bot.biological_systems.dt.datetime", _JanDateTime)
    jan_day = state.get_cycle_day()
    jan_profile = state.active_profile
    jan_month = state.profile_month
    assert jan_month == "2026-01"
    assert 1 <= jan_day <= state.cycle_length

    class _FebDateTime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return february_now if tz is not None else february_now.replace(tzinfo=None)

    monkeypatch.setattr("sel_bot.biological_systems.dt.datetime", _FebDateTime)
    feb_day = state.get_cycle_day()
    assert state.profile_month == "2026-02"
    assert 1 <= feb_day <= state.cycle_length
    # Monthly template may or may not change every month, but month key must update and remain coherent.
    assert state.active_profile in {"common_26", "common_28", "common_30", "common_32"}
    assert state.cycle_length in {26, 28, 30, 32}
    assert jan_profile in {"common_26", "common_28", "common_30", "common_32"}


def test_biological_state_roundtrip_menstrual_profile_fields() -> None:
    state = BiologicalState()
    state.menstrual.active_profile = "common_30"
    state.menstrual.profile_month = "2026-02"
    state.menstrual.cycle_length = 30
    state.menstrual.cycle_start_date = dt.datetime(2026, 2, 3, tzinfo=dt.timezone.utc)

    payload = state.to_dict()
    restored = BiologicalState.from_dict(payload)

    assert restored.menstrual.active_profile in {"common_26", "common_28", "common_30", "common_32"}
    assert restored.menstrual.profile_month is not None
    assert restored.menstrual.cycle_length in {26, 28, 30, 32}
    assert restored.menstrual.cycle_start_date is not None
