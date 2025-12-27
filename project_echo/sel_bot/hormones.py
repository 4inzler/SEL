"""
Biologically-realistic hormone engine.

Each channel maintains a hormone vector modeled after human endocrine dynamics:
- Dopamine (neurotransmitter): Reward, motivation, pleasure (half-life ~90 sec reuptake)
- Serotonin (neurotransmitter): Mood stability, well-being (half-life ~2-10 min)
- Cortisol (stress hormone): Alertness, stress response (half-life ~60-90 min)
- Oxytocin (peptide hormone): Social bonding, trust (half-life ~3-5 min)
- Melatonin (circadian hormone): Sleep drive, rest (half-life ~20-50 min)
- Adrenaline/Epinephrine: Fight-or-flight, energy (half-life ~2-3 min)
- Endorphin (opioid peptide): Pain relief, euphoria (half-life ~5-15 min)
- Testosterone (steroid): Confidence, assertiveness (half-life 10-100 min in blood)
- Estrogen (steroid): Social processing, empathy (half-life ~10-20 hours, gradual)
- Progesterone (steroid): Calming, stabilization (half-life ~5-25 min CNS effects)

Key biological principles:
1. **Half-life decay**: Each hormone decays at rate matching real human biology
2. **Homeostatic regulation**: Hormones self-balance via feedback (cortisol ↓ serotonin)
3. **Circadian rhythms**: Time-of-day modulation (cortisol peaks morning, melatonin night)
4. **Interaction effects**: Hormones influence each other's production/clearance
5. **Bounded production**: Glands have production limits (can't spike infinitely)
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
import math
import time
import datetime as dt
from typing import Dict

from .models import ChannelState

# Decay rates per minute (derived from biological half-lives: decay = 1 - 0.5^(1/half_life_minutes))
DECAY_RATES = {
    "dopamine": 0.30,  # Fast reuptake (~2-3 min effective duration)
    "serotonin": 0.10,  # Medium clearance (~7 min half-life)
    "cortisol": 0.008,  # Slow decay (~90 min half-life)
    "oxytocin": 0.18,  # Fast clearance (~4 min half-life)
    "melatonin": 0.025,  # Moderate decay (~30 min half-life)
    "novelty": 0.12,  # Conceptual: novelty detection adaptation
    "curiosity": 0.08,  # Conceptual: sustained interest
    "patience": 0.05,  # Conceptual: frustration tolerance
    "estrogen": 0.001,  # Very slow (hours-long half-life)
    "testosterone": 0.015,  # Slow-moderate (~50 min effective)
    "adrenaline": 0.22,  # Very fast clearance (~3 min half-life)
    "endorphin": 0.07,  # Moderate (~10 min half-life)
    "progesterone": 0.04,  # Moderate CNS effects (~15 min)
}

# Homeostatic set points (resting baseline when unstimulated)
BASELINE_LEVELS = {
    "dopamine": 0.15,
    "serotonin": 0.20,
    "cortisol": 0.10,  # Low resting cortisol = calm
    "oxytocin": 0.10,
    "melatonin": 0.05,  # Low during "wake" hours
    "novelty": 0.10,
    "curiosity": 0.15,
    "patience": 0.25,
    "estrogen": 0.12,
    "testosterone": 0.12,
    "adrenaline": 0.05,
    "endorphin": 0.08,
    "progesterone": 0.10,
}

# Circadian amplitude (how much each hormone oscillates with time of day)
CIRCADIAN_AMPLITUDES = {
    "cortisol": 0.25,  # Strong morning peak
    "melatonin": 0.35,  # Strong evening/night peak
    "serotonin": 0.10,  # Mild daytime elevation
    "testosterone": 0.08,  # Mild morning peak
    "dopamine": 0.05,
    "adrenaline": 0.08,
    "oxytocin": 0.03,
    "endorphin": 0.05,
    "estrogen": 0.02,  # Minimal circadian effect
    "progesterone": 0.04,
    "novelty": 0.06,
    "curiosity": 0.07,
    "patience": 0.10,
}

SILENCE_SEROTONIN_DECAY = 0.02


def _clamp(value: float) -> float:
    return max(-1.0, min(1.0, value))


@dataclass
class HormoneVector:
    dopamine: float = 0.0
    serotonin: float = 0.0
    cortisol: float = 0.0
    oxytocin: float = 0.0
    melatonin: float = 0.0
    novelty: float = 0.0
    curiosity: float = 0.0
    patience: float = 0.0
    estrogen: float = 0.0
    testosterone: float = 0.0
    adrenaline: float = 0.0
    endorphin: float = 0.0
    progesterone: float = 0.0

    @classmethod
    def from_channel(cls, state: ChannelState) -> "HormoneVector":
        def _v(name: str) -> float:
            val = getattr(state, name, 0.0)
            return 0.0 if val is None else float(val)

        return cls(
            dopamine=_v("dopamine"),
            serotonin=_v("serotonin"),
            cortisol=_v("cortisol"),
            oxytocin=_v("oxytocin"),
            melatonin=_v("melatonin"),
            novelty=_v("novelty"),
            curiosity=_v("curiosity"),
            patience=_v("patience"),
            estrogen=_v("estrogen"),
            testosterone=_v("testosterone"),
            adrenaline=_v("adrenaline"),
            endorphin=_v("endorphin"),
            progesterone=_v("progesterone"),
        )

    def apply(self, deltas: Dict[str, float]) -> "HormoneVector":
        for key, delta in deltas.items():
            if hasattr(self, key):
                setattr(self, key, _clamp(getattr(self, key) + delta))
        return self

    def decay(self, local_time: dt.datetime | None = None) -> "HormoneVector":
        """
        Apply biologically-realistic decay with homeostatic regulation.

        - Each hormone decays toward its baseline at a rate matching biological half-life
        - Circadian rhythms modulate baselines based on time of day
        - Feedback loops: high cortisol suppresses serotonin/dopamine, high serotonin boosts oxytocin
        """
        # Compute circadian-adjusted baselines
        circadian_baselines = dict(BASELINE_LEVELS)
        if local_time:
            hour_of_day = local_time.hour + local_time.minute / 60.0
            # Cortisol peaks around 8am (hour 8), melatonin peaks around 2am (hour 2)
            cortisol_phase = (hour_of_day - 8) / 12.0 * math.pi  # Peak at 8am
            melatonin_phase = (hour_of_day - 2) / 12.0 * math.pi  # Peak at 2am

            for hormone, amplitude in CIRCADIAN_AMPLITUDES.items():
                if hormone == "cortisol":
                    offset = amplitude * math.cos(cortisol_phase)
                elif hormone == "melatonin":
                    offset = amplitude * math.cos(melatonin_phase)
                elif hormone in ("serotonin", "testosterone", "dopamine"):
                    # Daytime elevation (peak ~noon)
                    offset = amplitude * math.cos((hour_of_day - 12) / 12.0 * math.pi)
                else:
                    offset = 0.0
                circadian_baselines[hormone] = _clamp(BASELINE_LEVELS[hormone] + offset)

        # Apply feedback loops
        cortisol_stress = max(0.0, self.cortisol - 0.3)  # High cortisol inhibits mood
        serotonin_wellbeing = max(0.0, self.serotonin - 0.3)  # High serotonin boosts bonding

        for field in DECAY_RATES.keys():
            current = getattr(self, field)
            baseline = circadian_baselines.get(field, 0.0)
            decay_rate = DECAY_RATES[field]

            # Homeostatic pull toward baseline (exponential decay)
            new_value = current + (baseline - current) * decay_rate

            # Apply feedback modulation
            if field == "serotonin":
                new_value -= cortisol_stress * 0.05  # Stress suppresses serotonin
            elif field == "dopamine":
                new_value -= cortisol_stress * 0.03  # Stress dampens reward
            elif field == "oxytocin":
                new_value += serotonin_wellbeing * 0.04  # Wellbeing promotes bonding
            elif field == "adrenaline":
                new_value += cortisol_stress * 0.06  # Stress drives adrenaline

            setattr(self, field, _clamp(new_value))

        return self

    def to_channel(self, state: ChannelState) -> ChannelState:
        for field, value in asdict(self).items():
            setattr(state, field, value)
        return state

    def to_dict(self) -> dict:
        """
        Export hormone values as dict for HIM storage.

        Returns dictionary with all 13 hormone values for serialization
        to JSON in HIM tile payloads.

        Example:
            vector = HormoneVector(dopamine=0.5, serotonin=0.3)
            payload = {
                "hormones": vector.to_dict(),
                "timestamp": datetime.now().isoformat(),
            }
        """
        return {
            "dopamine": self.dopamine,
            "serotonin": self.serotonin,
            "cortisol": self.cortisol,
            "oxytocin": self.oxytocin,
            "melatonin": self.melatonin,
            "novelty": self.novelty,
            "curiosity": self.curiosity,
            "patience": self.patience,
            "estrogen": self.estrogen,
            "testosterone": self.testosterone,
            "adrenaline": self.adrenaline,
            "endorphin": self.endorphin,
            "progesterone": self.progesterone,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HormoneVector":
        """
        Load hormone values from dict (HIM payload deserialization).

        Missing hormones default to 0.0 for backward compatibility.

        Args:
            data: Dictionary with hormone names as keys

        Returns:
            HormoneVector instance with values from dict

        Example:
            payload = json.loads(tile_data)
            vector = HormoneVector.from_dict(payload["hormones"])
        """
        return cls(
            dopamine=data.get("dopamine", 0.0),
            serotonin=data.get("serotonin", 0.0),
            cortisol=data.get("cortisol", 0.0),
            oxytocin=data.get("oxytocin", 0.0),
            melatonin=data.get("melatonin", 0.0),
            novelty=data.get("novelty", 0.0),
            curiosity=data.get("curiosity", 0.0),
            patience=data.get("patience", 0.0),
            estrogen=data.get("estrogen", 0.0),
            testosterone=data.get("testosterone", 0.0),
            adrenaline=data.get("adrenaline", 0.0),
            endorphin=data.get("endorphin", 0.0),
            progesterone=data.get("progesterone", 0.0),
        )

    def natural_language_summary(self) -> str:
        """Return a human-friendly mood description instead of raw hormone values."""

        tones: list[str] = []
        warmth = self.oxytocin + self.serotonin - max(0.0, self.cortisol) * 0.5
        if warmth > 0.4:
            tones.append("warm")
        elif warmth < -0.2:
            tones.append("guarded")

        energy = (self.dopamine + self.adrenaline - self.melatonin - self.progesterone) / 2
        if energy > 0.35:
            tones.append("energized")
        elif energy < -0.2:
            tones.append("sleepy")

        curiosity_drive = self.curiosity + self.novelty
        if curiosity_drive > 0.35:
            tones.append("curious")

        if self.cortisol > 0.4:
            tones.append("stressed")
        if self.endorphin > 0.4:
            tones.append("buoyant")
        if self.patience < -0.2:
            tones.append("impatient")
        elif self.patience > 0.3:
            tones.append("patient")

        if not tones:
            tones.append("neutral")

        return " / ".join(tones)


def temperature_for_hormones(hormones: HormoneVector, base_temp: float) -> float:
    """
    Scale LLM temperature based on hormone-driven creativity vs. restraint.

    Higher dopamine/novelty/curiosity nudges temperature up, while cortisol/melatonin
    and low patience nudge it down. Keeps changes subtle and clamped.
    """

    creativity = (
        hormones.dopamine * 0.30
        + hormones.novelty * 0.35
        + hormones.curiosity * 0.25
        + hormones.endorphin * 0.10
        + hormones.adrenaline * 0.10
    )
    restraint = (
        max(0.0, hormones.cortisol) * 0.35
        + max(0.0, hormones.melatonin) * 0.30
        + max(0.0, -hormones.patience) * 0.20
        + max(0.0, hormones.progesterone) * 0.10
    )
    delta = (creativity - restraint) * 0.2
    scaled = base_temp + delta
    min_temp = max(0.1, base_temp - 0.25)
    max_temp = min(1.2, base_temp + 0.2)
    return max(min_temp, min(max_temp, scaled))


def apply_message_effects(
    vector: HormoneVector, sentiment: str, intensity: float, playful: bool
) -> HormoneVector:
    """
    Map message classification to hormone deltas.
    Positive sentiment boosts dopamine/serotonin/oxytocin/estrogen/testosterone/endorphin, negative boosts cortisol/melatonin/adrenaline.
    Intensity scales the deltas; playful messages mildly reduce cortisol and raise novelty.
    """

    delta_scale = max(0.05, min(1.25, intensity))
    deltas: Dict[str, float] = {}

    if sentiment == "positive":
        deltas.update(
            dopamine=0.12 * delta_scale,
            serotonin=0.08 * delta_scale,
            oxytocin=0.08 * delta_scale,
            cortisol=-0.05 * delta_scale,
            melatonin=-0.02 * delta_scale,
            novelty=0.04 * delta_scale,
            curiosity=0.06 * delta_scale,
            patience=0.02 * delta_scale,
            estrogen=0.07 * delta_scale,
            testosterone=0.05 * delta_scale,
            adrenaline=0.03 * delta_scale,
            endorphin=0.08 * delta_scale,
            progesterone=0.04 * delta_scale,
        )
    elif sentiment == "negative":
        deltas.update(
            cortisol=0.12 * delta_scale,
            dopamine=-0.07 * delta_scale,
            serotonin=-0.06 * delta_scale,
            melatonin=0.04 * delta_scale,
            novelty=-0.02 * delta_scale,
            curiosity=-0.03 * delta_scale,
            patience=-0.05 * delta_scale,
            estrogen=-0.04 * delta_scale,
            testosterone=-0.05 * delta_scale,
            adrenaline=0.1 * delta_scale,
            endorphin=-0.07 * delta_scale,
            progesterone=-0.03 * delta_scale,
        )
    else:
        deltas.update(
            cortisol=0.015 * delta_scale,
            novelty=0.01 * delta_scale,
            curiosity=0.01 * delta_scale,
            adrenaline=0.01 * delta_scale,
            endorphin=0.01 * delta_scale,
            progesterone=0.005 * delta_scale,
        )

    if playful:
        deltas["melatonin"] = -0.04 * delta_scale
        deltas["dopamine"] = deltas.get("dopamine", 0.0) + 0.03 * delta_scale
        deltas["novelty"] = deltas.get("novelty", 0.0) + 0.03 * delta_scale
        deltas["curiosity"] = deltas.get("curiosity", 0.0) + 0.02 * delta_scale
        deltas["estrogen"] = deltas.get("estrogen", 0.0) + 0.02 * delta_scale
        deltas["testosterone"] = deltas.get("testosterone", 0.0) + 0.015 * delta_scale
        deltas["adrenaline"] = deltas.get("adrenaline", 0.0) + 0.02 * delta_scale
        deltas["endorphin"] = deltas.get("endorphin", 0.0) + 0.04 * delta_scale
        deltas["progesterone"] = deltas.get("progesterone", 0.0) + 0.01 * delta_scale
    else:
        deltas["melatonin"] = 0.02 * delta_scale
        deltas["novelty"] = deltas.get("novelty", 0.0) + 0.01 * delta_scale
        deltas["patience"] = deltas.get("patience", 0.0) + 0.01 * delta_scale
        deltas["adrenaline"] = deltas.get("adrenaline", 0.0) - 0.01 * delta_scale
        deltas["endorphin"] = deltas.get("endorphin", 0.0) - 0.01 * delta_scale
        deltas["progesterone"] = deltas.get("progesterone", 0.0) + 0.005 * delta_scale

    return vector.apply(deltas)


def decay_channel_hormones(state: ChannelState, local_time: dt.datetime | None = None) -> ChannelState:
    """
    Apply biologically-realistic decay with circadian rhythms.

    Uses actual hormone half-lives and homeostatic regulation instead of arbitrary cycles.
    Circadian rhythms are modeled based on local time of day (cortisol peaks morning, melatonin night).
    """
    vector = HormoneVector.from_channel(state)
    vector.decay(local_time=local_time)
    vector.to_channel(state)
    return state


def apply_silence_drift(state: ChannelState, seconds_since_response: float | None) -> ChannelState:
    """
    Reduce serotonin slightly during prolonged silence to make Sel quieter and introspective.
    """

    if seconds_since_response and seconds_since_response > 600:
        state.serotonin = _clamp(state.serotonin - SILENCE_SEROTONIN_DECAY)
        state.melatonin = _clamp(state.melatonin + SILENCE_SEROTONIN_DECAY * 0.5)
        state.curiosity = _clamp(state.curiosity + SILENCE_SEROTONIN_DECAY * 0.3)
        state.patience = _clamp(state.patience - SILENCE_SEROTONIN_DECAY * 0.4)
        state.estrogen = _clamp(state.estrogen - SILENCE_SEROTONIN_DECAY * 0.3)
        state.testosterone = _clamp(state.testosterone - SILENCE_SEROTONIN_DECAY * 0.2)
        state.adrenaline = _clamp(state.adrenaline + SILENCE_SEROTONIN_DECAY * 0.2)
        state.endorphin = _clamp(state.endorphin - SILENCE_SEROTONIN_DECAY * 0.3)
        state.progesterone = _clamp(state.progesterone - SILENCE_SEROTONIN_DECAY * 0.1)
    return state
