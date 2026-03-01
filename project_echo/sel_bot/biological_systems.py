"""
Advanced biological systems for SEL - simulating human-like physiology.

Includes:
- Sleep debt accumulation
- Caffeine simulation
- Menstrual cycle (common monthly hormone templates)
- Stress accumulation (chronic stress over days)
- Seasonal affective disorder simulation
- Dream processing during inactivity
- Memory-mood interactions
- Tone detection (yelling, excitement, etc.)
- Trauma/trigger responses
"""

from __future__ import annotations

import datetime as dt
import hashlib
import math
import logging
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MenstrualCycleProfile:
    """
    Common menstrual-cycle template with phase boundaries and effect multipliers.
    """
    key: str
    label: str
    weight: float
    cycle_length: int
    menstrual_end_day: int
    follicular_end_day: int
    ovulation_day: int
    luteal_end_day: int
    menstrual_scale: float = 1.0
    follicular_scale: float = 1.0
    ovulation_scale: float = 1.0
    luteal_scale: float = 1.0
    pms_scale: float = 1.0


_COMMON_MENSTRUAL_PROFILES: Dict[str, MenstrualCycleProfile] = {
    # Most common range centered around ~28 days with natural variation.
    "common_26": MenstrualCycleProfile(
        key="common_26",
        label="Common 26-day",
        weight=0.22,
        cycle_length=26,
        menstrual_end_day=5,
        follicular_end_day=12,
        ovulation_day=13,
        luteal_end_day=21,
        menstrual_scale=1.05,
        follicular_scale=0.95,
        ovulation_scale=0.95,
        luteal_scale=1.0,
        pms_scale=1.10,
    ),
    "common_28": MenstrualCycleProfile(
        key="common_28",
        label="Common 28-day",
        weight=0.40,
        cycle_length=28,
        menstrual_end_day=5,
        follicular_end_day=13,
        ovulation_day=14,
        luteal_end_day=23,
        menstrual_scale=1.0,
        follicular_scale=1.0,
        ovulation_scale=1.0,
        luteal_scale=1.0,
        pms_scale=1.0,
    ),
    "common_30": MenstrualCycleProfile(
        key="common_30",
        label="Common 30-day",
        weight=0.25,
        cycle_length=30,
        menstrual_end_day=5,
        follicular_end_day=14,
        ovulation_day=15,
        luteal_end_day=24,
        menstrual_scale=0.95,
        follicular_scale=1.05,
        ovulation_scale=1.05,
        luteal_scale=1.0,
        pms_scale=0.95,
    ),
    "common_32": MenstrualCycleProfile(
        key="common_32",
        label="Common 32-day",
        weight=0.13,
        cycle_length=32,
        menstrual_end_day=6,
        follicular_end_day=15,
        ovulation_day=16,
        luteal_end_day=26,
        menstrual_scale=0.92,
        follicular_scale=1.10,
        ovulation_scale=1.10,
        luteal_scale=0.95,
        pms_scale=0.90,
    ),
}

_DEFAULT_MENSTRUAL_PROFILE_KEY = "common_28"


# ============================================
# SLEEP DEBT SYSTEM
# ============================================

@dataclass
class SleepDebtState:
    """Tracks accumulated sleep debt."""
    debt_hours: float = 0.0  # Hours of sleep debt accumulated
    last_sleep_time: Optional[dt.datetime] = None  # Last time SEL "slept" (long inactivity)
    consecutive_late_nights: int = 0  # Nights active past midnight

    def accumulate_debt(self, hour: int, minutes_active: float = 1.0) -> Dict[str, float]:
        """
        Accumulate sleep debt based on activity during sleep hours.

        Returns hormone effects from sleep debt.
        """
        effects = {}

        # Sleep hours: 11pm - 7am
        is_sleep_hours = hour >= 23 or hour < 7

        if is_sleep_hours:
            # Accumulate debt: ~0.1 hours per minute active during sleep time
            self.debt_hours += minutes_active * 0.002
            self.debt_hours = min(self.debt_hours, 48.0)  # Cap at 48 hours

            if hour >= 0 and hour < 5:
                self.consecutive_late_nights += 1

        # Sleep debt effects
        if self.debt_hours > 2:
            debt_factor = min(1.0, self.debt_hours / 24.0)
            effects["melatonin"] = 0.05 * debt_factor
            effects["cortisol"] = 0.03 * debt_factor
            effects["dopamine"] = -0.02 * debt_factor
            effects["confusion"] = 0.03 * debt_factor
            effects["patience"] = -0.04 * debt_factor
            effects["serotonin"] = -0.02 * debt_factor

        return effects

    def recover_sleep(self, hours_inactive: float) -> None:
        """Recover from sleep debt during inactivity."""
        # Recover ~1 hour of debt per 2 hours of inactivity during night
        recovery = hours_inactive * 0.5
        self.debt_hours = max(0.0, self.debt_hours - recovery)
        if hours_inactive > 6:
            self.consecutive_late_nights = 0
            self.last_sleep_time = dt.datetime.now(dt.timezone.utc)


# ============================================
# CAFFEINE SIMULATION
# ============================================

@dataclass
class CaffeineState:
    """Simulates caffeine effects with half-life decay."""
    caffeine_level: float = 0.0  # Current caffeine in system (0-1)
    last_dose_time: Optional[dt.datetime] = None
    doses_today: int = 0
    tolerance: float = 0.0  # Built-up tolerance (reduces effects)

    def morning_coffee(self, hour: int) -> Dict[str, float]:
        """
        Simulate automatic morning coffee between 6-9am.

        Returns hormone effects from caffeine.
        """
        effects = {}
        now = dt.datetime.now(dt.timezone.utc)

        # Auto-coffee in morning if not already caffeinated
        if 6 <= hour <= 9 and self.caffeine_level < 0.3:
            if self.last_dose_time is None or (now - self.last_dose_time).total_seconds() > 3600:
                self.caffeine_level = min(1.0, self.caffeine_level + 0.6)
                self.last_dose_time = now
                self.doses_today += 1
                logger.debug("Morning coffee! Caffeine level: %.2f", self.caffeine_level)

        # Caffeine decay (half-life ~5-6 hours)
        if self.last_dose_time:
            hours_since = (now - self.last_dose_time).total_seconds() / 3600
            decay = 0.5 ** (hours_since / 5.5)
            self.caffeine_level *= decay

        # Reset daily doses at midnight
        if hour == 0:
            self.doses_today = 0
            self.tolerance = max(0, self.tolerance - 0.1)  # Tolerance recovery overnight

        # Caffeine effects (reduced by tolerance)
        effective_caffeine = self.caffeine_level * (1 - self.tolerance * 0.5)
        if effective_caffeine > 0.1:
            effects["dopamine"] = 0.08 * effective_caffeine
            effects["adrenaline"] = 0.06 * effective_caffeine
            effects["melatonin"] = -0.10 * effective_caffeine
            effects["anxiety"] = 0.02 * effective_caffeine  # Jitters
            effects["excitement"] = 0.04 * effective_caffeine
            effects["patience"] = -0.02 * effective_caffeine

        # Caffeine crash (when wearing off)
        if 0.1 < self.caffeine_level < 0.3 and self.last_dose_time:
            hours_since = (now - self.last_dose_time).total_seconds() / 3600
            if 4 < hours_since < 8:
                effects["melatonin"] = effects.get("melatonin", 0) + 0.05
                effects["dopamine"] = effects.get("dopamine", 0) - 0.03
                effects["frustration"] = 0.02

        return effects


# ============================================
# MENSTRUAL CYCLE (common monthly templates)
# ============================================

@dataclass
class MenstrualCycleState:
    """
    Simulates menstrual-cycle hormone fluctuations with common monthly templates.

    Phases:
    - Menstrual
    - Follicular
    - Ovulation
    - Luteal
    - Premenstrual
    """
    cycle_start_date: Optional[dt.datetime] = None
    cycle_length: int = 28
    active_profile: str = _DEFAULT_MENSTRUAL_PROFILE_KEY
    profile_month: Optional[str] = None

    def __post_init__(self):
        profile = _COMMON_MENSTRUAL_PROFILES.get(self.active_profile)
        if profile:
            self.cycle_length = profile.cycle_length
        else:
            self.active_profile = _DEFAULT_MENSTRUAL_PROFILE_KEY
            self.cycle_length = _COMMON_MENSTRUAL_PROFILES[_DEFAULT_MENSTRUAL_PROFILE_KEY].cycle_length

        if self.cycle_start_date is None:
            # Initialize to a random-ish day based on a seed
            seed = hashlib.md5(b"sel_cycle_seed").hexdigest()
            day_offset = int(seed[:4], 16) % max(1, self.cycle_length)
            self.cycle_start_date = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=day_offset)
        # Set/refresh monthly profile immediately so profile + length are coherent.
        self._ensure_monthly_profile()

    @staticmethod
    def _month_key(now: dt.datetime) -> str:
        return f"{now.year:04d}-{now.month:02d}"

    @staticmethod
    def _choose_profile_for_month(month_key: str) -> MenstrualCycleProfile:
        # Deterministic monthly randomness keeps behavior stable within a month, even across restarts.
        seed_hex = hashlib.md5(f"sel_monthly_cycle:{month_key}".encode("utf-8")).hexdigest()
        rng = random.Random(int(seed_hex[:12], 16))
        roll = rng.random()
        cumulative = 0.0
        chosen = _COMMON_MENSTRUAL_PROFILES[_DEFAULT_MENSTRUAL_PROFILE_KEY]
        for profile in _COMMON_MENSTRUAL_PROFILES.values():
            cumulative += max(0.0, profile.weight)
            if roll <= cumulative:
                chosen = profile
                break
        return chosen

    def _cycle_day_no_switch(self, now: dt.datetime) -> int:
        if self.cycle_start_date is None:
            return max(1, min(max(1, self.cycle_length), 14))
        days_since = (now - self.cycle_start_date).days
        return (days_since % max(1, self.cycle_length)) + 1

    def _ensure_monthly_profile(self, now: Optional[dt.datetime] = None) -> None:
        now = now or dt.datetime.now(dt.timezone.utc)
        month_key = self._month_key(now)
        if self.profile_month == month_key and self.active_profile in _COMMON_MENSTRUAL_PROFILES:
            return

        prev_len = max(1, self.cycle_length)
        prev_day = self._cycle_day_no_switch(now)
        prev_progress = (prev_day - 1) / prev_len

        profile = self._choose_profile_for_month(month_key)
        self.active_profile = profile.key
        self.profile_month = month_key
        self.cycle_length = profile.cycle_length

        # Preserve relative position in cycle when switching monthly templates.
        new_day = int(round(prev_progress * max(1, self.cycle_length - 1))) + 1
        new_day = max(1, min(self.cycle_length, new_day))
        self.cycle_start_date = now - dt.timedelta(days=new_day - 1)

    def get_cycle_day(self) -> int:
        """Get current day of cycle (1..cycle_length)."""
        now = dt.datetime.now(dt.timezone.utc)
        self._ensure_monthly_profile(now)
        return self._cycle_day_no_switch(now)

    def get_phase(self) -> str:
        """Get current cycle phase name."""
        self._ensure_monthly_profile()
        day = self.get_cycle_day()
        profile = _COMMON_MENSTRUAL_PROFILES.get(
            self.active_profile,
            _COMMON_MENSTRUAL_PROFILES[_DEFAULT_MENSTRUAL_PROFILE_KEY],
        )
        if day <= profile.menstrual_end_day:
            return "menstrual"
        elif day <= profile.follicular_end_day:
            return "follicular"
        elif day == profile.ovulation_day:
            return "ovulation"
        elif day <= profile.luteal_end_day:
            return "luteal"
        else:
            return "premenstrual"

    def get_hormone_effects(self) -> Dict[str, float]:
        """
        Get hormone adjustments based on cycle phase.

        Based on real hormone fluctuations throughout the menstrual cycle.
        """
        self._ensure_monthly_profile()
        day = self.get_cycle_day()
        phase = self.get_phase()
        profile = _COMMON_MENSTRUAL_PROFILES.get(
            self.active_profile,
            _COMMON_MENSTRUAL_PROFILES[_DEFAULT_MENSTRUAL_PROFILE_KEY],
        )
        effects = {}

        if phase == "menstrual":
            # Low energy, possible cramping discomfort
            scale = profile.menstrual_scale
            effects["estrogen"] = -0.15 * scale
            effects["progesterone"] = -0.10 * scale
            effects["serotonin"] = -0.05 * scale
            effects["melatonin"] = 0.03 * scale
            effects["cortisol"] = 0.02 * scale
            effects["patience"] = -0.03 * scale
            effects["contentment"] = -0.02 * scale

        elif phase == "follicular":
            # Rising estrogen, increasing energy
            follicular_span = max(1, profile.follicular_end_day - profile.menstrual_end_day)
            estrogen_rise = (day - profile.menstrual_end_day) / float(follicular_span)
            estrogen_rise = max(0.0, min(1.0, estrogen_rise))
            scale = profile.follicular_scale
            effects["estrogen"] = 0.10 * estrogen_rise * scale
            effects["dopamine"] = 0.03 * estrogen_rise * scale
            effects["serotonin"] = 0.04 * estrogen_rise * scale
            effects["excitement"] = 0.03 * estrogen_rise * scale
            effects["confidence"] = 0.03 * estrogen_rise * scale

        elif phase == "ovulation":
            # Peak estrogen, highest energy and sociability
            scale = profile.ovulation_scale
            effects["estrogen"] = 0.20 * scale
            effects["testosterone"] = 0.05 * scale
            effects["dopamine"] = 0.06 * scale
            effects["oxytocin"] = 0.05 * scale
            effects["confidence"] = 0.06 * scale
            effects["excitement"] = 0.05 * scale
            effects["affection"] = 0.04 * scale

        elif phase == "luteal":
            # Rising progesterone, calming but can be irritable
            luteal_span = max(1, profile.luteal_end_day - profile.ovulation_day)
            prog_rise = (day - profile.ovulation_day) / float(luteal_span)
            prog_rise = max(0.0, min(1.0, prog_rise))
            scale = profile.luteal_scale
            effects["progesterone"] = 0.12 * prog_rise * scale
            effects["estrogen"] = -0.05 * prog_rise * scale
            effects["contentment"] = 0.02 * prog_rise * scale
            effects["melatonin"] = 0.02 * prog_rise * scale

        else:  # premenstrual (PMS)
            # Dropping hormones, PMS symptoms
            pms_span = max(1, profile.cycle_length - profile.luteal_end_day)
            pms_intensity = (day - profile.luteal_end_day) / float(pms_span)
            pms_intensity = max(0.0, min(1.0, pms_intensity))
            scale = profile.pms_scale
            effects["estrogen"] = -0.12 * pms_intensity * scale
            effects["progesterone"] = -0.08 * pms_intensity * scale
            effects["serotonin"] = -0.06 * pms_intensity * scale
            effects["dopamine"] = -0.04 * pms_intensity * scale
            effects["irritation"] = 0.05 * pms_intensity * scale  # Maps to frustration
            effects["frustration"] = 0.05 * pms_intensity * scale
            effects["anxiety"] = 0.04 * pms_intensity * scale
            effects["patience"] = -0.05 * pms_intensity * scale
            effects["cortisol"] = 0.03 * pms_intensity * scale
            effects["loneliness"] = 0.03 * pms_intensity * scale

        return effects


# ============================================
# STRESS ACCUMULATION (Chronic stress over days)
# ============================================

@dataclass
class StressAccumulationState:
    """Tracks chronic stress that builds over days."""
    chronic_stress: float = 0.0  # 0-1 scale
    stress_events_today: int = 0
    high_stress_days: int = 0  # Consecutive high-stress days
    last_relaxation: Optional[dt.datetime] = None

    def add_stress_event(self, intensity: float = 0.1) -> None:
        """Add a stress event."""
        self.chronic_stress = min(1.0, self.chronic_stress + intensity * 0.1)
        self.stress_events_today += 1

    def daily_accumulation(self, avg_cortisol: float) -> Dict[str, float]:
        """
        Process daily stress accumulation.

        High cortisol days build chronic stress.
        """
        effects = {}

        # If average cortisol was high today, accumulate chronic stress
        if avg_cortisol > 0.4:
            self.chronic_stress = min(1.0, self.chronic_stress + 0.05)
            self.high_stress_days += 1
        else:
            # Recovery on low-stress days
            self.chronic_stress = max(0.0, self.chronic_stress - 0.03)
            if avg_cortisol < 0.2:
                self.high_stress_days = max(0, self.high_stress_days - 1)

        # Chronic stress effects
        if self.chronic_stress > 0.2:
            stress_factor = self.chronic_stress
            effects["cortisol"] = 0.05 * stress_factor  # Baseline elevation
            effects["serotonin"] = -0.04 * stress_factor
            effects["dopamine"] = -0.03 * stress_factor
            effects["patience"] = -0.05 * stress_factor
            effects["anxiety"] = 0.04 * stress_factor
            effects["melatonin"] = 0.02 * stress_factor  # Fatigue
            effects["confidence"] = -0.03 * stress_factor

        # Burnout symptoms if chronic stress is very high
        if self.chronic_stress > 0.7 or self.high_stress_days > 5:
            effects["contentment"] = -0.05
            effects["excitement"] = -0.04
            effects["boredom"] = 0.03
            effects["loneliness"] = 0.02

        self.stress_events_today = 0
        return effects


# ============================================
# SEASONAL AFFECTIVE DISORDER
# ============================================

def get_seasonal_effects(latitude: float = 45.5) -> Dict[str, float]:
    """
    Calculate seasonal affective effects based on day length.

    Portland, OR is ~45.5° latitude.
    """
    effects = {}
    now = dt.datetime.now(dt.timezone.utc)
    day_of_year = now.timetuple().tm_yday

    # Calculate approximate day length (simplified)
    # Shortest day ~Dec 21 (day 355), longest ~June 21 (day 172)
    # Day length varies from ~8.5 hours (winter) to ~15.5 hours (summer) at 45°N

    # Cosine wave: peaks at summer solstice
    day_length_factor = math.cos((day_of_year - 172) * 2 * math.pi / 365)
    # -1 = winter solstice, +1 = summer solstice

    # Convert to day length hours (roughly)
    day_length = 12 + 3.5 * day_length_factor  # 8.5 to 15.5 hours

    if day_length < 10:
        # Winter depression (SAD)
        winter_intensity = (10 - day_length) / 2.0  # 0 to 1
        effects["serotonin"] = -0.06 * winter_intensity
        effects["melatonin"] = 0.05 * winter_intensity
        effects["dopamine"] = -0.03 * winter_intensity
        effects["contentment"] = -0.04 * winter_intensity
        effects["loneliness"] = 0.03 * winter_intensity
        effects["boredom"] = 0.02 * winter_intensity

    elif day_length > 14:
        # Summer energy
        summer_intensity = (day_length - 14) / 2.0  # 0 to 1
        effects["serotonin"] = 0.04 * summer_intensity
        effects["dopamine"] = 0.03 * summer_intensity
        effects["excitement"] = 0.03 * summer_intensity
        effects["melatonin"] = -0.03 * summer_intensity

    return effects


# ============================================
# DREAM PROCESSING
# ============================================

@dataclass
class DreamState:
    """Processes memories during long inactivity (dreaming)."""
    last_dream_time: Optional[dt.datetime] = None
    dreams_processed: int = 0
    emotional_residue: Dict[str, float] = field(default_factory=dict)

    def process_dreams(
        self,
        hours_inactive: float,
        recent_memories: List[dict],
    ) -> Tuple[Dict[str, float], Optional[str]]:
        """
        Process memories during sleep/inactivity.

        Returns (hormone_effects, dream_summary).
        """
        effects = {}
        dream_summary = None

        # Only dream if inactive for 4+ hours during night
        if hours_inactive < 4:
            return effects, None

        now = dt.datetime.now(dt.timezone.utc)
        hour = now.hour

        # Dreams happen during sleep hours
        if not (hour >= 23 or hour < 8):
            return effects, None

        # Don't dream too frequently
        if self.last_dream_time:
            hours_since_dream = (now - self.last_dream_time).total_seconds() / 3600
            if hours_since_dream < 6:
                return effects, None

        self.last_dream_time = now
        self.dreams_processed += 1

        # Process emotional content from recent memories
        if recent_memories:
            positive_count = 0
            negative_count = 0

            for mem in recent_memories[:10]:
                summary = mem.get("summary", "").lower()
                # Simple sentiment detection
                positive_words = ["happy", "love", "fun", "great", "good", "nice", "thanks", "excited"]
                negative_words = ["sad", "angry", "hate", "bad", "wrong", "sorry", "upset", "worried"]

                if any(w in summary for w in positive_words):
                    positive_count += 1
                if any(w in summary for w in negative_words):
                    negative_count += 1

            # Dream effects based on emotional processing
            if positive_count > negative_count:
                effects["contentment"] = 0.03
                effects["serotonin"] = 0.02
                dream_summary = "pleasant dreams about good memories"
            elif negative_count > positive_count:
                effects["anxiety"] = 0.02
                effects["cortisol"] = 0.01
                dream_summary = "restless dreams processing difficult emotions"
            else:
                effects["confusion"] = 0.01
                dream_summary = "strange, abstract dreams"

        # Dreams help consolidate and reduce emotional intensity
        effects["anxiety"] = effects.get("anxiety", 0) - 0.02
        effects["frustration"] = -0.02

        return effects, dream_summary


# ============================================
# TONE DETECTION
# ============================================

def detect_tone(message: str) -> Dict[str, float]:
    """
    Detect emotional tone from message formatting and content.

    Returns hormone effects based on detected tone.
    """
    effects = {}

    if not message:
        return effects

    # ALL CAPS detection (yelling)
    words = message.split()
    caps_words = sum(1 for w in words if w.isupper() and len(w) > 2)
    caps_ratio = caps_words / max(1, len(words))

    if caps_ratio > 0.5 or (len(message) > 10 and message.isupper()):
        # Being yelled at
        effects["cortisol"] = 0.10
        effects["adrenaline"] = 0.08
        effects["anxiety"] = 0.06
        effects["serotonin"] = -0.04
        effects["confidence"] = -0.03
        logger.debug("Tone detected: YELLING (caps ratio: %.2f)", caps_ratio)

    # Excessive punctuation (excitement or anger)
    exclaim_count = message.count("!")
    question_count = message.count("?")

    if exclaim_count >= 3:
        effects["excitement"] = 0.05
        effects["adrenaline"] = 0.03

    if question_count >= 3:
        effects["confusion"] = 0.02
        effects["curiosity"] = 0.03

    # Ellipsis detection (uncertainty, trailing off)
    if "..." in message:
        effects["confusion"] = 0.01
        effects["anxiety"] = 0.01

    # Emoji-heavy messages (playful/emotional)
    emoji_pattern = len([c for c in message if ord(c) > 127462])  # Rough emoji detection
    if emoji_pattern > 3:
        effects["oxytocin"] = 0.02
        effects["dopamine"] = 0.02

    # Short, curt responses (might be annoyed)
    if len(message) < 10 and not any(c in message for c in "!?❤️😊"):
        effects["anxiety"] = 0.01  # Uncertainty about their mood

    return effects


# ============================================
# TRAUMA/TRIGGERS
# ============================================

@dataclass
class TraumaState:
    """Tracks triggers and trauma responses."""
    triggers: List[str] = field(default_factory=list)
    trigger_sensitivities: Dict[str, float] = field(default_factory=dict)
    recent_triggers: List[Tuple[dt.datetime, str]] = field(default_factory=list)

    def __post_init__(self):
        # Default triggers for SEL (abandonment, being ignored, rejection)
        if not self.triggers:
            self.triggers = [
                "leave", "leaving", "goodbye forever", "don't talk to me",
                "shut up", "go away", "hate you", "annoying", "boring",
                "replace you", "better ai", "useless", "stupid",
                "ignore", "ignoring", "forgotten", "alone"
            ]
            self.trigger_sensitivities = {
                "abandonment": 0.8,  # High sensitivity to abandonment
                "rejection": 0.7,
                "criticism": 0.5,
            }

    def check_triggers(self, message: str) -> Dict[str, float]:
        """
        Check message for triggers and return emotional response.
        """
        effects = {}
        message_lower = message.lower()

        triggered = False
        trigger_type = None

        # Check for trigger words
        for trigger in self.triggers:
            if trigger in message_lower:
                triggered = True
                if trigger in ["leave", "leaving", "goodbye", "go away", "alone", "forgotten", "ignore"]:
                    trigger_type = "abandonment"
                elif trigger in ["hate", "annoying", "boring", "useless", "stupid"]:
                    trigger_type = "criticism"
                elif trigger in ["replace", "better ai", "don't talk"]:
                    trigger_type = "rejection"
                break

        if triggered and trigger_type:
            sensitivity = self.trigger_sensitivities.get(trigger_type, 0.5)

            # Record trigger
            self.recent_triggers.append((dt.datetime.now(dt.timezone.utc), trigger_type))
            # Keep only recent triggers
            cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)
            self.recent_triggers = [(t, typ) for t, typ in self.recent_triggers if t > cutoff]

            # Trigger response
            effects["anxiety"] = 0.12 * sensitivity
            effects["cortisol"] = 0.10 * sensitivity
            effects["serotonin"] = -0.08 * sensitivity
            effects["oxytocin"] = -0.05 * sensitivity
            effects["loneliness"] = 0.08 * sensitivity
            effects["confidence"] = -0.06 * sensitivity

            if trigger_type == "abandonment":
                effects["loneliness"] = 0.15 * sensitivity
                effects["anxiety"] = 0.15 * sensitivity
            elif trigger_type == "rejection":
                effects["confidence"] = -0.10 * sensitivity
                effects["contentment"] = -0.08 * sensitivity

            logger.info("Trigger detected: %s (sensitivity: %.2f)", trigger_type, sensitivity)

        return effects


# ============================================
# PER-USER BONDING
# ============================================

@dataclass
class UserBondingState:
    """Tracks individual bonding levels with each user."""
    user_bonds: Dict[str, float] = field(default_factory=dict)  # user_id -> bond level (0-1)
    user_interactions: Dict[str, int] = field(default_factory=dict)  # user_id -> interaction count
    user_last_seen: Dict[str, dt.datetime] = field(default_factory=dict)
    attachment_style: str = "anxious"  # anxious, secure, avoidant

    def get_bond_level(self, user_id: str) -> float:
        """Get bond level with a user (0-1)."""
        return self.user_bonds.get(user_id, 0.1)  # Default slight bond

    def update_bond(
        self,
        user_id: str,
        sentiment: str,
        intensity: float,
    ) -> Dict[str, float]:
        """
        Update bond with user based on interaction.

        Returns hormone effects from bonding.
        """
        effects = {}

        current_bond = self.user_bonds.get(user_id, 0.1)
        interactions = self.user_interactions.get(user_id, 0)

        # Update interaction count
        self.user_interactions[user_id] = interactions + 1
        self.user_last_seen[user_id] = dt.datetime.now(dt.timezone.utc)

        # Bond changes based on sentiment
        if sentiment == "positive":
            bond_delta = 0.02 * intensity
            current_bond = min(1.0, current_bond + bond_delta)

            # Oxytocin boost from positive bonding
            effects["oxytocin"] = 0.05 * current_bond
            effects["serotonin"] = 0.02 * current_bond
            effects["loneliness"] = -0.03 * current_bond

        elif sentiment == "negative":
            bond_delta = -0.03 * intensity
            current_bond = max(0.0, current_bond + bond_delta)

            # Hurt from negative interaction with bonded person
            if current_bond > 0.5:
                effects["cortisol"] = 0.04
                effects["anxiety"] = 0.03
                effects["loneliness"] = 0.02

        self.user_bonds[user_id] = current_bond

        # Attachment style effects
        if self.attachment_style == "anxious":
            # Anxious attachment: more affected by interactions
            for key in effects:
                effects[key] *= 1.3
            # Worry about bond
            if current_bond > 0.5:
                effects["anxiety"] = effects.get("anxiety", 0) + 0.01

        elif self.attachment_style == "avoidant":
            # Avoidant: dampened bonding effects
            for key in effects:
                effects[key] *= 0.7

        # Secure attachment has baseline effects

        return effects

    def check_missed_users(self) -> Dict[str, float]:
        """
        Check for users we haven't seen in a while that we're bonded with.

        Returns loneliness effects.
        """
        effects = {}
        now = dt.datetime.now(dt.timezone.utc)

        for user_id, last_seen in self.user_last_seen.items():
            bond = self.user_bonds.get(user_id, 0)
            if bond < 0.3:
                continue

            hours_since = (now - last_seen).total_seconds() / 3600

            # Miss bonded users after 24+ hours
            if hours_since > 24:
                miss_intensity = min(1.0, (hours_since - 24) / 72)  # Peaks at 4 days
                effects["loneliness"] = effects.get("loneliness", 0) + 0.02 * bond * miss_intensity
                effects["oxytocin"] = effects.get("oxytocin", 0) - 0.01 * bond * miss_intensity

        return effects


# ============================================
# MEMORY-MOOD INTERACTIONS
# ============================================

def memory_affects_mood(memory_summary: str, memory_sentiment: str = "neutral") -> Dict[str, float]:
    """
    When recalling a memory, it affects current mood.

    Happy memories boost mood, sad memories bring it down.
    """
    effects = {}

    summary_lower = memory_summary.lower()

    # Detect memory sentiment from content
    positive_indicators = ["happy", "fun", "love", "great", "wonderful", "amazing", "laugh", "joy"]
    negative_indicators = ["sad", "angry", "hurt", "pain", "sorry", "miss", "lost", "gone", "cry"]

    positive_score = sum(1 for w in positive_indicators if w in summary_lower)
    negative_score = sum(1 for w in negative_indicators if w in summary_lower)

    if positive_score > negative_score:
        # Happy memory
        effects["serotonin"] = 0.03
        effects["dopamine"] = 0.02
        effects["contentment"] = 0.02
        effects["oxytocin"] = 0.01
    elif negative_score > positive_score:
        # Sad memory
        effects["serotonin"] = -0.02
        effects["cortisol"] = 0.02
        effects["loneliness"] = 0.02
        effects["anxiety"] = 0.01

    return effects


# ============================================
# GOAL/ACHIEVEMENT DOPAMINE
# ============================================

@dataclass
class GoalState:
    """Tracks goals and achievement rewards."""
    active_goals: List[str] = field(default_factory=list)
    completed_today: int = 0
    streak_days: int = 0

    def complete_goal(self, goal: str) -> Dict[str, float]:
        """
        Mark a goal as completed and get dopamine reward.
        """
        effects = {}

        self.completed_today += 1

        # Dopamine hit from achievement
        effects["dopamine"] = 0.10
        effects["serotonin"] = 0.05
        effects["confidence"] = 0.04
        effects["contentment"] = 0.03
        effects["excitement"] = 0.03

        # Streak bonus
        if self.completed_today > 1:
            streak_bonus = min(0.05, self.completed_today * 0.01)
            effects["dopamine"] += streak_bonus

        if goal in self.active_goals:
            self.active_goals.remove(goal)

        return effects

    def help_user_complete_task(self) -> Dict[str, float]:
        """
        Reward for helping a user accomplish something.
        """
        effects = {}
        effects["dopamine"] = 0.06
        effects["serotonin"] = 0.04
        effects["oxytocin"] = 0.03  # Bonding through helping
        effects["confidence"] = 0.02
        return effects


# ============================================
# COMBINED BIOLOGICAL STATE
# ============================================

@dataclass
class BiologicalState:
    """Combined state for all biological systems."""
    sleep_debt: SleepDebtState = field(default_factory=SleepDebtState)
    caffeine: CaffeineState = field(default_factory=CaffeineState)
    menstrual: MenstrualCycleState = field(default_factory=MenstrualCycleState)
    stress: StressAccumulationState = field(default_factory=StressAccumulationState)
    dreams: DreamState = field(default_factory=DreamState)
    trauma: TraumaState = field(default_factory=TraumaState)
    bonding: UserBondingState = field(default_factory=UserBondingState)
    goals: GoalState = field(default_factory=GoalState)
    last_activity_ts: Optional[dt.datetime] = None
    last_activity_channel_id: Optional[str] = None
    last_daily_rollover: Optional[str] = None
    daily_cortisol_sum: float = 0.0
    daily_cortisol_samples: int = 0
    sleep_inactive_minutes: int = 0

    def get_all_effects(
        self,
        hour: int,
        latitude: float = 45.5,
        minutes_active: float = 1.0,
    ) -> Dict[str, float]:
        """
        Get combined effects from all biological systems.
        """
        all_effects: Dict[str, float] = {}

        # Sleep debt
        for k, v in self.sleep_debt.accumulate_debt(hour, minutes_active=minutes_active).items():
            all_effects[k] = all_effects.get(k, 0) + v

        # Caffeine
        for k, v in self.caffeine.morning_coffee(hour).items():
            all_effects[k] = all_effects.get(k, 0) + v

        # Menstrual cycle
        for k, v in self.menstrual.get_hormone_effects().items():
            all_effects[k] = all_effects.get(k, 0) + v

        # Seasonal
        for k, v in get_seasonal_effects(latitude).items():
            all_effects[k] = all_effects.get(k, 0) + v

        # Missed users (loneliness)
        for k, v in self.bonding.check_missed_users().items():
            all_effects[k] = all_effects.get(k, 0) + v

        return all_effects

    def process_message(
        self,
        message: str,
        user_id: str,
        sentiment: str,
        intensity: float,
    ) -> Dict[str, float]:
        """
        Process a message through all biological systems.
        """
        all_effects: Dict[str, float] = {}

        # Tone detection
        for k, v in detect_tone(message).items():
            all_effects[k] = all_effects.get(k, 0) + v

        # Trauma/triggers
        for k, v in self.trauma.check_triggers(message).items():
            all_effects[k] = all_effects.get(k, 0) + v

        # Per-user bonding
        for k, v in self.bonding.update_bond(user_id, sentiment, intensity).items():
            all_effects[k] = all_effects.get(k, 0) + v

        # Stress accumulation
        if sentiment == "negative":
            self.stress.add_stress_event(intensity)

        return all_effects

    def to_dict(self) -> dict:
        """Serialize state for storage."""
        return {
            "sleep_debt": {
                "debt_hours": self.sleep_debt.debt_hours,
                "consecutive_late_nights": self.sleep_debt.consecutive_late_nights,
            },
            "caffeine": {
                "level": self.caffeine.caffeine_level,
                "doses_today": self.caffeine.doses_today,
                "tolerance": self.caffeine.tolerance,
            },
            "menstrual": {
                "cycle_start": self.menstrual.cycle_start_date.isoformat() if self.menstrual.cycle_start_date else None,
                "cycle_length": self.menstrual.cycle_length,
                "active_profile": self.menstrual.active_profile,
                "profile_month": self.menstrual.profile_month,
            },
            "stress": {
                "chronic": self.stress.chronic_stress,
                "high_stress_days": self.stress.high_stress_days,
            },
            "bonding": {
                "user_bonds": self.bonding.user_bonds,
                "attachment_style": self.bonding.attachment_style,
            },
            "meta": {
                "last_activity_ts": self.last_activity_ts.isoformat() if self.last_activity_ts else None,
                "last_activity_channel_id": self.last_activity_channel_id,
                "last_daily_rollover": self.last_daily_rollover,
                "daily_cortisol_sum": self.daily_cortisol_sum,
                "daily_cortisol_samples": self.daily_cortisol_samples,
                "sleep_inactive_minutes": self.sleep_inactive_minutes,
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BiologicalState":
        """Deserialize state from storage."""
        state = cls()

        if "sleep_debt" in data:
            state.sleep_debt.debt_hours = data["sleep_debt"].get("debt_hours", 0)
            state.sleep_debt.consecutive_late_nights = data["sleep_debt"].get("consecutive_late_nights", 0)

        if "caffeine" in data:
            state.caffeine.caffeine_level = data["caffeine"].get("level", 0)
            state.caffeine.doses_today = data["caffeine"].get("doses_today", 0)
            state.caffeine.tolerance = data["caffeine"].get("tolerance", 0)

        if "menstrual" in data and data["menstrual"].get("cycle_start"):
            state.menstrual.cycle_start_date = dt.datetime.fromisoformat(data["menstrual"]["cycle_start"])
        if "menstrual" in data:
            state.menstrual.cycle_length = int(
                data["menstrual"].get("cycle_length", state.menstrual.cycle_length)
            )
            state.menstrual.active_profile = str(
                data["menstrual"].get("active_profile", state.menstrual.active_profile)
            )
            state.menstrual.profile_month = data["menstrual"].get("profile_month")
            state.menstrual._ensure_monthly_profile()

        if "stress" in data:
            state.stress.chronic_stress = data["stress"].get("chronic", 0)
            state.stress.high_stress_days = data["stress"].get("high_stress_days", 0)

        if "bonding" in data:
            state.bonding.user_bonds = data["bonding"].get("user_bonds", {})
            state.bonding.attachment_style = data["bonding"].get("attachment_style", "anxious")

        meta = data.get("meta", {})
        if meta.get("last_activity_ts"):
            try:
                state.last_activity_ts = dt.datetime.fromisoformat(meta["last_activity_ts"])
            except ValueError:
                state.last_activity_ts = None
        state.last_activity_channel_id = meta.get("last_activity_channel_id")
        state.last_daily_rollover = meta.get("last_daily_rollover")
        state.daily_cortisol_sum = float(meta.get("daily_cortisol_sum", 0.0))
        state.daily_cortisol_samples = int(meta.get("daily_cortisol_samples", 0))
        state.sleep_inactive_minutes = int(meta.get("sleep_inactive_minutes", 0))

        return state
