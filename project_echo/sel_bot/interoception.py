"""Synthetic interoception model for Sel's body-like awareness."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Mapping, Optional

from .hormones import HormoneVector


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class InteroceptionEngine:
    """
    Tracks synthetic body-state signals (fatigue, arousal, stress, social need, etc).
    Optional sensor telemetry can be dropped into JSONL and automatically folded in.
    """

    def __init__(self, settings: Any, *, repo_root: Optional[Path] = None) -> None:
        self.settings = settings
        self.repo_root = (repo_root or Path(__file__).resolve().parents[2]).resolve()
        self.data_dir = self._resolve_sel_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.data_dir / "interoception_log.jsonl"
        self.latest_path = self.data_dir / "interoception_latest.json"
        self.sensor_path = self._resolve_sensor_stream_path()

    def _resolve_sel_data_dir(self) -> Path:
        data_dir = Path(getattr(self.settings, "sel_data_dir", "./sel_data")).expanduser()
        if not data_dir.is_absolute():
            data_dir = (self.repo_root / data_dir).resolve()
        return data_dir

    def _resolve_sensor_stream_path(self) -> Path:
        raw = str(getattr(self.settings, "sel_interoception_sensor_stream_path", "") or "").strip()
        if raw:
            path = Path(raw).expanduser()
            if not path.is_absolute():
                path = (self.repo_root / path).resolve()
            return path
        return self.data_dir / "sensor_stream.jsonl"

    def read_latest_sensor_payload(self, *, max_lines: int = 120) -> dict[str, Any]:
        if not self.sensor_path.exists():
            return {}
        try:
            lines = self.sensor_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            return {}
        if not lines:
            return {}
        for line in reversed(lines[-max_lines:]):
            try:
                parsed = json.loads(line)
            except Exception:
                continue
            if isinstance(parsed, dict):
                return parsed
        return {}

    def compute_snapshot(
        self,
        *,
        bio_state: Any,
        hormones: HormoneVector,
        trigger: str,
        local_hour: Optional[int] = None,
        environment_alignment: Optional[float] = None,
        sensor_payload: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        sensor = dict(sensor_payload or {})
        sleep_debt_hours = _coerce_float(
            getattr(getattr(bio_state, "sleep_debt", None), "debt_hours", 0.0),
            default=0.0,
        )
        chronic_stress = _coerce_float(
            getattr(getattr(bio_state, "stress", None), "chronic_stress", 0.0),
            default=0.0,
        )
        sleep_inactive_minutes = _coerce_float(getattr(bio_state, "sleep_inactive_minutes", 0.0), default=0.0)
        daily_cortisol_samples = _coerce_float(getattr(bio_state, "daily_cortisol_samples", 0.0), default=0.0)

        fatigue = _clamp(
            (max(0.0, hormones.melatonin) * 0.52)
            + (max(0.0, sleep_debt_hours) / 24.0 * 0.48)
        )
        stress_load = _clamp(
            (max(0.0, hormones.cortisol) * 0.44)
            + (max(0.0, hormones.anxiety) * 0.32)
            + (max(0.0, chronic_stress) * 0.24)
        )
        social_need = _clamp(
            (max(0.0, hormones.loneliness) * 0.7)
            + (max(0.0, 0.2 - hormones.oxytocin) * 0.45)
        )
        cognitive_load = _clamp(
            (max(0.0, hormones.confusion) * 0.38)
            + (max(0.0, hormones.frustration) * 0.34)
            + (max(0.0, hormones.boredom) * 0.28)
        )
        arousal = _clamp(
            (max(0.0, hormones.adrenaline) * 0.45)
            + (max(0.0, hormones.excitement) * 0.35)
            + (max(0.0, hormones.dopamine) * 0.20)
        )
        mood_stability = _clamp(
            (max(0.0, hormones.contentment) * 0.34)
            + (max(0.0, hormones.serotonin) * 0.32)
            + (max(0.0, hormones.patience) * 0.20)
            + (max(0.0, hormones.confidence) * 0.14)
            - (stress_load * 0.35)
        )
        sensory_load = _clamp((max(0.0, hormones.excitement) * 0.24) + (stress_load * 0.22))

        if local_hour is None:
            local_hour = dt.datetime.now(dt.timezone.utc).hour
        circadian_pressure = _clamp(
            0.9 if local_hour >= 23 or local_hour < 5 else 0.65 if local_hour < 7 else 0.28 if local_hour < 11 else 0.45
        )

        env_alignment = _clamp(_coerce_float(environment_alignment, default=0.5))
        adaptation_drive = _clamp((1.0 - env_alignment) * 0.55 + (max(0.0, hormones.curiosity) * 0.45))

        # Optional sensor stream inputs.
        heart_rate = _coerce_float(sensor.get("heart_rate"), default=0.0)
        noise_db = _coerce_float(sensor.get("noise_db"), default=0.0)
        screen_minutes = _coerce_float(sensor.get("screen_minutes"), default=0.0)

        if heart_rate > 0:
            if heart_rate >= 96:
                stress_load = _clamp(stress_load + 0.08)
                arousal = _clamp(arousal + 0.07)
            elif heart_rate <= 56:
                fatigue = _clamp(fatigue + 0.04)
        if noise_db > 0:
            if noise_db >= 75:
                sensory_load = _clamp(sensory_load + 0.12)
                cognitive_load = _clamp(cognitive_load + 0.05)
            elif noise_db <= 35:
                mood_stability = _clamp(mood_stability + 0.03)
        if screen_minutes > 0:
            if screen_minutes >= 240:
                fatigue = _clamp(fatigue + 0.06)
                cognitive_load = _clamp(cognitive_load + 0.08)
            elif screen_minutes <= 40:
                mood_stability = _clamp(mood_stability + 0.02)

        energy_budget = _clamp((max(0.0, hormones.dopamine) * 0.45) + (max(0.0, hormones.endorphin) * 0.25) - (fatigue * 0.42))
        sleep_drive = _clamp((circadian_pressure * 0.6) + (fatigue * 0.4))

        mode = "balanced"
        if stress_load >= 0.72 or sensory_load >= 0.72:
            mode = "overloaded"
        elif sleep_drive >= 0.72:
            mode = "drowsy"
        elif arousal >= 0.72 and fatigue < 0.55:
            mode = "wired"
        elif cognitive_load >= 0.68:
            mode = "strained"
        elif mood_stability >= 0.65 and stress_load < 0.4:
            mode = "steady"

        summary = (
            f"interoceptive mode={mode}; fatigue={fatigue:.2f}, stress={stress_load:.2f}, "
            f"social_need={social_need:.2f}, cognitive_load={cognitive_load:.2f}, "
            f"sleep_drive={sleep_drive:.2f}, stability={mood_stability:.2f}"
        )
        if sensor:
            summary += "; sensor_stream=active"

        return {
            "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "trigger": trigger,
            "mode": mode,
            "summary": summary,
            "metrics": {
                "fatigue": round(fatigue, 4),
                "stress_load": round(stress_load, 4),
                "social_need": round(social_need, 4),
                "cognitive_load": round(cognitive_load, 4),
                "arousal": round(arousal, 4),
                "mood_stability": round(mood_stability, 4),
                "sensory_load": round(sensory_load, 4),
                "circadian_pressure": round(circadian_pressure, 4),
                "adaptation_drive": round(adaptation_drive, 4),
                "energy_budget": round(energy_budget, 4),
                "sleep_drive": round(sleep_drive, 4),
            },
            "sleep_debt_hours": round(sleep_debt_hours, 3),
            "sleep_inactive_minutes": round(sleep_inactive_minutes, 3),
            "daily_cortisol_samples": int(daily_cortisol_samples),
            "environment_alignment": round(env_alignment, 4),
            "sensor": sensor,
        }

    def persist_snapshot(self, snapshot: Mapping[str, Any], *, max_entries: int = 4000) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        payload = dict(snapshot)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
        try:
            self.latest_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        except Exception:
            pass
        self._trim_log(max_entries=max_entries)

    def _trim_log(self, *, max_entries: int) -> None:
        if max_entries <= 0 or not self.log_path.exists():
            return
        try:
            lines = self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            return
        if len(lines) <= max_entries:
            return
        kept = lines[-max_entries:]
        self.log_path.write_text("\n".join(kept) + "\n", encoding="utf-8")

    def load_recent(self, *, limit: int = 6) -> list[dict[str, Any]]:
        if limit <= 0 or not self.log_path.exists():
            return []
        try:
            lines = self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            return []
        output: list[dict[str, Any]] = []
        for line in lines[-limit:]:
            try:
                parsed = json.loads(line)
            except Exception:
                continue
            if isinstance(parsed, dict):
                output.append(parsed)
        return output
