from __future__ import annotations

from types import SimpleNamespace

from sel_bot.hormones import HormoneVector
from sel_bot.prompts import derive_style_guidance


def _global_state():
    return SimpleNamespace(
        preferred_length="medium",
        emoji_rate=0.5,
        teasing_level=0.5,
    )


def _user_state():
    return SimpleNamespace(
        prefers_short_replies=False,
        emoji_preference="medium",
        irritation=0.0,
        likes_teasing=True,
        bond=0.8,
    )


def _sample_content() -> str:
    return "i have been testing this setup for a while and wanted to compare options before i pick one"


def test_style_guidance_fatigue_pushes_short_focused_reply() -> None:
    neutral = derive_style_guidance(
        global_state=_global_state(),
        user_state=_user_state(),
        sentiment="positive",
        intensity=0.4,
        playful=True,
        user_content=_sample_content(),
        direct_question=False,
        hormones=HormoneVector(),
    )
    fatigued = derive_style_guidance(
        global_state=_global_state(),
        user_state=_user_state(),
        sentiment="positive",
        intensity=0.4,
        playful=True,
        user_content=_sample_content(),
        direct_question=False,
        hormones=HormoneVector(melatonin=0.9, cortisol=0.7, anxiety=0.6, confusion=0.5),
    )
    assert neutral.length == "medium"
    assert fatigued.length == "short"
    assert fatigued.tone == "focused"
    assert fatigued.pacing == "single"


def test_style_guidance_warm_curious_mood_enables_multi_pacing() -> None:
    style = derive_style_guidance(
        global_state=_global_state(),
        user_state=_user_state(),
        sentiment="positive",
        intensity=0.4,
        playful=True,
        user_content=_sample_content(),
        direct_question=False,
        hormones=HormoneVector(
            oxytocin=0.8,
            endorphin=0.7,
            affection=0.7,
            curiosity=0.8,
            novelty=0.7,
            dopamine=0.6,
            excitement=0.6,
        ),
    )
    assert style.tone == "playful"
    assert style.pacing == "multi"
    assert style.emoji_level == "high"
    assert style.teasing == "playful"


def test_style_guidance_tension_increases_directness() -> None:
    style = derive_style_guidance(
        global_state=_global_state(),
        user_state=_user_state(),
        sentiment="positive",
        intensity=0.4,
        playful=True,
        user_content=_sample_content(),
        direct_question=False,
        hormones=HormoneVector(cortisol=0.9, anxiety=0.8, frustration=0.7, patience=-0.4),
    )
    assert style.directness == "high"
    assert style.tone == "focused"
    assert style.length == "short"
