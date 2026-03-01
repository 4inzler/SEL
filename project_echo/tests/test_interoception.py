from __future__ import annotations

import types
from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy")

from sel_bot.hormones import HormoneVector
from sel_bot.interoception import InteroceptionEngine


def _settings(tmp_path: Path):
    return types.SimpleNamespace(
        sel_data_dir=str(tmp_path / "sel_data"),
        sel_interoception_sensor_stream_path="",
    )


def _bio_state_stub():
    sleep_debt = types.SimpleNamespace(debt_hours=6.0)
    stress = types.SimpleNamespace(chronic_stress=0.35)
    return types.SimpleNamespace(
        sleep_debt=sleep_debt,
        stress=stress,
        sleep_inactive_minutes=42,
        daily_cortisol_samples=5,
    )


def test_compute_snapshot_metrics_in_range(tmp_path: Path) -> None:
    engine = InteroceptionEngine(_settings(tmp_path), repo_root=tmp_path)
    snapshot = engine.compute_snapshot(
        bio_state=_bio_state_stub(),
        hormones=HormoneVector(
            dopamine=0.3,
            serotonin=0.22,
            cortisol=0.4,
            oxytocin=0.08,
            melatonin=0.3,
            novelty=0.15,
            curiosity=0.21,
            patience=0.18,
            anxiety=0.35,
            excitement=0.2,
            frustration=0.26,
            contentment=0.15,
            loneliness=0.4,
            confidence=0.2,
            confusion=0.28,
            boredom=0.15,
            endorphin=0.1,
            adrenaline=0.18,
        ),
        trigger="test",
        local_hour=2,
        environment_alignment=0.42,
        sensor_payload={"heart_rate": 101, "noise_db": 79},
    )
    metrics = snapshot["metrics"]
    assert snapshot["mode"] in {"overloaded", "drowsy", "wired", "strained", "steady", "balanced"}
    assert all(0.0 <= float(value) <= 1.0 for value in metrics.values())


def test_persist_snapshot_trims_log(tmp_path: Path) -> None:
    engine = InteroceptionEngine(_settings(tmp_path), repo_root=tmp_path)
    for i in range(6):
        engine.persist_snapshot(
            {
                "timestamp_utc": f"2026-01-01T00:00:0{i}+00:00",
                "trigger": "test",
                "mode": "balanced",
                "metrics": {"fatigue": 0.2},
            },
            max_entries=3,
        )
    lines = engine.log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    recent = engine.load_recent(limit=2)
    assert len(recent) == 2
