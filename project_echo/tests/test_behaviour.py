from __future__ import annotations

from sel_bot.behaviour import (
    engagement_pressure_from_hormones,
    extract_greeting_target,
    is_broadcast_greeting_target,
    is_direct_question_to_sel,
    score_addressee_intent,
    should_respond,
)
from sel_bot.hormones import HormoneVector


def test_should_respond_on_mention() -> None:
    hormones = HormoneVector()
    assert should_respond(
        is_mentioned=True,
        direct_question=False,
        hormones=hormones,
        base_chance=0.0,
        messages_since_response=0,
        seconds_since_response=None,
    )


def test_should_respond_backlog_for_continuation() -> None:
    hormones = HormoneVector(dopamine=1.0, endorphin=0.8, estrogen=1.0)
    assert not should_respond(
        is_mentioned=False,
        direct_question=False,
        hormones=hormones,
        base_chance=0.0,
        messages_since_response=0,
        seconds_since_response=None,
        is_continuation=True,
    )
    assert should_respond(
        is_mentioned=False,
        direct_question=False,
        hormones=hormones,
        base_chance=0.0,
        messages_since_response=5,
        seconds_since_response=None,
        is_continuation=True,
    )


def test_direct_question_word_boundary() -> None:
    assert not is_direct_question_to_sel("myself?", "sel")
    assert is_direct_question_to_sel("Sel?", "sel")
    assert is_direct_question_to_sel("hey, sel?", "Sel")


def test_extract_greeting_target() -> None:
    assert extract_greeting_target("hi pandemic") == "pandemic"
    assert extract_greeting_target("Hello, @Rin") == "rin"
    assert extract_greeting_target("good morning folks") == "folks"
    assert extract_greeting_target("what's up") is None


def test_broadcast_greeting_targets() -> None:
    assert is_broadcast_greeting_target("everyone")
    assert is_broadcast_greeting_target("Folks")
    assert not is_broadcast_greeting_target("pandemic")


def test_score_addressee_intent_targets_sel_on_name_and_question() -> None:
    result = score_addressee_intent(
        "sel can you help me with this?",
        "sel",
        is_reply_to_sel=False,
        is_reply_to_other=False,
        is_mentioned_sel=False,
        mentioned_other_names=[],
        recent_other_names=[],
        recent_speaker_counts={"ayla": 1},
        recent_sel_messages=0,
        recent_author_messages=1,
        greeting_target=None,
        force_addressed=False,
    )
    assert result["addressed_to_sel"]
    assert not result["addressed_to_other"]


def test_score_addressee_intent_targets_other_on_reply_and_name() -> None:
    result = score_addressee_intent(
        "hey rinexis what do you think?",
        "sel",
        is_reply_to_sel=False,
        is_reply_to_other=True,
        is_mentioned_sel=False,
        mentioned_other_names=["rinexis"],
        recent_other_names=["rinexis", "travis"],
        recent_speaker_counts={"ayla": 2, "rinexis": 2, "travis": 1},
        recent_sel_messages=1,
        recent_author_messages=2,
        greeting_target="rinexis",
        force_addressed=False,
    )
    assert result["addressed_to_other"]
    assert not result["addressed_to_sel"]


def test_score_addressee_intent_uses_recent_exchange_for_continuation() -> None:
    result = score_addressee_intent(
        "what about the thing you said earlier?",
        "sel",
        is_reply_to_sel=False,
        is_reply_to_other=False,
        is_mentioned_sel=False,
        mentioned_other_names=[],
        recent_other_names=[],
        recent_speaker_counts={"ayla": 2},
        recent_sel_messages=3,
        recent_author_messages=2,
        greeting_target=None,
        force_addressed=False,
    )
    assert result["continuation_hint"]


def test_score_addressee_intent_prefers_other_on_reply_to_other() -> None:
    result = score_addressee_intent(
        "what do you think about that?",
        "sel",
        is_reply_to_sel=False,
        is_reply_to_other=True,
        is_mentioned_sel=False,
        mentioned_other_names=[],
        recent_other_names=["rinexis"],
        recent_speaker_counts={"ayla": 2, "rinexis": 1},
        recent_sel_messages=2,
        recent_author_messages=2,
        greeting_target=None,
        force_addressed=False,
    )
    assert result["addressed_to_other"]
    assert not result["addressed_to_sel"]


def test_score_addressee_intent_allows_explicit_sel_question_in_reply_thread() -> None:
    result = score_addressee_intent(
        "sel can you answer this?",
        "sel",
        is_reply_to_sel=False,
        is_reply_to_other=True,
        is_mentioned_sel=False,
        mentioned_other_names=[],
        recent_other_names=["rinexis"],
        recent_speaker_counts={"ayla": 2, "rinexis": 1},
        recent_sel_messages=2,
        recent_author_messages=2,
        greeting_target=None,
        force_addressed=False,
    )
    assert result["addressed_to_sel"]
    assert not result["addressed_to_other"]


def test_engagement_pressure_from_hormones_penalizes_reply_to_other() -> None:
    hormones = HormoneVector(
        dopamine=0.7,
        oxytocin=0.6,
        curiosity=0.8,
        novelty=0.6,
        endorphin=0.5,
        excitement=0.5,
        cortisol=0.05,
        melatonin=0.05,
        patience=0.1,
    )
    neutral_pressure = engagement_pressure_from_hormones(hormones, is_continuation=True, replying_to_other=False)
    reply_other_pressure = engagement_pressure_from_hormones(
        hormones,
        is_continuation=True,
        replying_to_other=True,
    )
    assert neutral_pressure > reply_other_pressure


def test_engagement_pressure_from_hormones_drops_with_stress_and_fatigue() -> None:
    energized = HormoneVector(
        dopamine=0.6,
        oxytocin=0.5,
        curiosity=0.6,
        endorphin=0.5,
        cortisol=0.05,
        melatonin=0.05,
        anxiety=0.05,
    )
    stressed = HormoneVector(
        dopamine=0.1,
        oxytocin=0.0,
        curiosity=0.0,
        endorphin=0.0,
        cortisol=0.8,
        melatonin=0.7,
        anxiety=0.7,
        frustration=0.6,
        boredom=0.4,
        confusion=0.4,
        patience=0.6,
    )
    assert engagement_pressure_from_hormones(energized) > engagement_pressure_from_hormones(stressed)
