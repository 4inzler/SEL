from __future__ import annotations

from sel_bot.behaviour import is_direct_question_to_sel, should_respond
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
    hormones = HormoneVector()
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
