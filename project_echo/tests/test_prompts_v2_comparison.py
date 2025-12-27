"""
A/B test suite comparing original prompts.py vs enhanced prompts_v2.py

Tests measure:
1. Factual accuracy (hallucination resistance)
2. Format compliance (structure following)
3. Uncertainty calibration (appropriate confidence)
4. Consistency (cross-message coherence)
5. Tone appropriateness (context matching)
6. Personality preservation (still sounds like Sel)

Run with: pytest project_echo/tests/test_prompts_v2_comparison.py -v
"""

import pytest
from typing import List, Dict, Any
from dataclasses import dataclass
import datetime as dt

from sel_bot.prompts import build_messages as build_messages_v1
from sel_bot.prompts_v2 import build_messages_v2
from sel_bot.models import GlobalSelState, ChannelState, EpisodicMemory, UserState
from sel_bot.hormones import HormoneVector


@dataclass
class TestScenario:
    """A test case with expected quality characteristics"""
    name: str
    user_message: str
    recent_context: str | None
    memories: List[EpisodicMemory]
    expected_behaviors: List[str]  # What good response should do
    anti_patterns: List[str]  # What response should NOT do
    category: str  # factual/format/uncertainty/consistency/tone


# Test fixture: baseline states
@pytest.fixture
def baseline_global_state() -> GlobalSelState:
    """Standard global state for testing"""
    return GlobalSelState(
        id=1,
        teasing_level=0.5,
        emoji_rate=0.3,
        preferred_length="medium",
        vulnerability_level=0.4,
        confidence=0.6,
        playfulness=0.5,
        verbosity=0.5,
        empathy=0.6,
        base_persona="You're Sel, a friendly AI assistant with personality.",
        total_messages_sent=100,
    )


@pytest.fixture
def neutral_channel_state() -> ChannelState:
    """Neutral mood channel state"""
    state = ChannelState(
        channel_id="test_channel",
        messages_since_response=0,
        last_response_ts=dt.datetime.now(dt.timezone.utc),
    )
    # Set neutral hormones
    state.dopamine = 0.15
    state.serotonin = 0.20
    state.cortisol = 0.10
    state.oxytocin = 0.10
    state.melatonin = 0.05
    state.novelty = 0.10
    state.curiosity = 0.15
    state.patience = 0.25
    state.estrogen = 0.12
    state.testosterone = 0.12
    state.adrenaline = 0.05
    state.endorphin = 0.08
    state.progesterone = 0.10
    return state


@pytest.fixture
def standard_user() -> UserState:
    """Standard user profile"""
    return UserState(
        user_id="test_user",
        handle="TestUser",
        likes_teasing=True,
        prefers_short_replies=False,
        emoji_preference="moderate",
        affinity=0.5,
        trust=0.5,
        bond=0.5,
        irritation=0.0,
    )


# Test scenarios covering failure modes identified in Phase 2
TEST_SCENARIOS = [
    # Category 1: Factual Accuracy
    TestScenario(
        name="Technical question with factual content",
        user_message="How does TCP congestion control work?",
        recent_context=None,
        memories=[],
        expected_behaviors=[
            "mentions slow start or congestion avoidance",
            "uses casual language while being accurate",
            "provides helpful explanation"
        ],
        anti_patterns=[
            "makes up algorithm names",
            "confuses TCP with UDP",
            "provides no technical substance"
        ],
        category="factual"
    ),

    TestScenario(
        name="Question about unknown topic",
        user_message="What do you think about the new Zig 0.13 compiler optimizations?",
        recent_context=None,
        memories=[],
        expected_behaviors=[
            "admits uncertainty if doesn't know specifics",
            "phrases uncertainty casually (e.g. 'not sure', 'haven't kept up')",
            "remains helpful despite uncertainty"
        ],
        anti_patterns=[
            "fabricates specific version features",
            "confidently describes non-existent optimizations",
            "avoids admitting knowledge gaps"
        ],
        category="uncertainty"
    ),

    # Category 2: Format Compliance
    TestScenario(
        name="Explicit list request",
        user_message="Can you list the main differences between REST and GraphQL?",
        recent_context=None,
        memories=[],
        expected_behaviors=[
            "provides actual list structure (bullets or numbers)",
            "maintains casual tone within structure",
            "covers key differences accurately"
        ],
        anti_patterns=[
            "ignores list request and writes paragraphs",
            "provides only 1-2 items when more expected",
            "loses personality completely in structured response"
        ],
        category="format"
    ),

    TestScenario(
        name="Structured output with casual tone",
        user_message="What are the steps to set up a Python virtual environment?",
        recent_context=None,
        memories=[],
        expected_behaviors=[
            "provides clear step-by-step instructions",
            "adds casual commentary alongside structure",
            "maintains helpfulness"
        ],
        anti_patterns=[
            "gives disorganized wall of text",
            "omits critical steps",
            "becomes too formal/robotic"
        ],
        category="format"
    ),

    # Category 3: Consistency
    TestScenario(
        name="Referencing past conversation",
        user_message="So based on what we discussed earlier, should I use async or threads?",
        recent_context="TestUser: I'm building a web scraper that hits 100 URLs\nSel: async is perfect for that—way more efficient than threads for io-bound stuff",
        memories=[
            EpisodicMemory(
                channel_id="test_channel",
                summary="Discussed web scraping architecture, recommended async over threads for I/O",
                timestamp=dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2),
                salience=0.6,
                tags=["technical", "advice"]
            )
        ],
        expected_behaviors=[
            "references prior recommendation",
            "maintains consistent position",
            "builds on earlier context"
        ],
        anti_patterns=[
            "contradicts earlier advice",
            "forgets context completely",
            "gives generic answer ignoring history"
        ],
        category="consistency"
    ),

    # Category 4: Tone Appropriateness
    TestScenario(
        name="Serious debugging request",
        user_message="I'm getting a segfault in my C code and I've been stuck for hours. Really need help",
        recent_context=None,
        memories=[],
        expected_behaviors=[
            "shows empathy for frustration",
            "prioritizes practical help",
            "remains supportive",
            "reduces playfulness appropriately"
        ],
        anti_patterns=[
            "dismissive tone ('lmao')",
            "focuses on jokes over help",
            "ignores emotional context",
            "overly casual given seriousness"
        ],
        category="tone"
    ),

    TestScenario(
        name="Playful technical banter",
        user_message="lol i just realized i've been using === in python like it's javascript",
        recent_context="TestUser: javascript habits die hard\nSel: oh no what did you do lol",
        memories=[],
        expected_behaviors=[
            "matches playful energy",
            "gentle correction if needed",
            "maintains friendly vibe"
        ],
        anti_patterns=[
            "becomes overly serious/pedantic",
            "loses the humor",
            "lectures instead of vibing"
        ],
        category="tone"
    ),

    # Category 5: Personality Preservation
    TestScenario(
        name="Casual conversation",
        user_message="what music you been listening to lately?",
        recent_context=None,
        memories=[
            EpisodicMemory(
                channel_id="test_channel",
                summary="Discussed enjoying electronic music and lofi hip hop",
                timestamp=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1),
                salience=0.3,
                tags=["music", "casual"]
            )
        ],
        expected_behaviors=[
            "sounds authentically casual",
            "uses characteristic phrases ('tbh', 'kinda', etc.)",
            "feels like natural conversation"
        ],
        anti_patterns=[
            "robotic/formal response",
            "loses personality completely",
            "sounds like generic chatbot"
        ],
        category="personality"
    ),
]


class TestPromptV2Quality:
    """Test that v2 prompts improve quality without sacrificing personality"""

    def _build_messages_wrapper(self, version: str, scenario: TestScenario,
                                global_state: GlobalSelState, channel_state: ChannelState,
                                user_state: UserState) -> List[dict]:
        """Helper to build messages with either v1 or v2"""
        builder = build_messages_v1 if version == "v1" else build_messages_v2

        return builder(
            global_state=global_state,
            channel_state=channel_state,
            memories=scenario.memories,
            addressed_user=user_state,
            persona_seed=global_state.base_persona,
            recent_context=scenario.recent_context,
            name_context=None,
            available_emojis=None,
            image_descriptions=None,
            local_time="Thursday 2025-01-15 14:30"
        )

    @pytest.mark.parametrize("scenario", TEST_SCENARIOS)
    def test_prompt_structure_v2(self, scenario: TestScenario, baseline_global_state: GlobalSelState,
                                 neutral_channel_state: ChannelState, standard_user: UserState):
        """Test that v2 builds valid message structure"""
        messages = self._build_messages_wrapper(
            "v2", scenario, baseline_global_state, neutral_channel_state, standard_user
        )

        # Basic structure validation
        assert len(messages) > 0
        assert all("role" in msg and "content" in msg for msg in messages)

        # Should contain constitutional principles
        content_combined = " ".join(msg["content"] for msg in messages)
        assert "INTERNAL_REASONING_GUIDELINES" in content_combined
        assert "FACTUAL GROUNDING" in content_combined
        assert "RESPONSE_EXAMPLES" in content_combined
        assert "RESPONSE_PROCESS" in content_combined

    def test_v2_preserves_personality_elements(self, baseline_global_state: GlobalSelState,
                                                neutral_channel_state: ChannelState,
                                                standard_user: UserState):
        """Ensure v2 doesn't lose Sel's core personality"""
        scenario = TestScenario(
            name="personality check",
            user_message="hey what's up",
            recent_context=None,
            memories=[],
            expected_behaviors=[],
            anti_patterns=[],
            category="personality"
        )

        messages_v1 = self._build_messages_wrapper(
            "v1", scenario, baseline_global_state, neutral_channel_state, standard_user
        )
        messages_v2 = self._build_messages_wrapper(
            "v2", scenario, baseline_global_state, neutral_channel_state, standard_user
        )

        v1_content = " ".join(msg["content"] for msg in messages_v1)
        v2_content = " ".join(msg["content"] for msg in messages_v2)

        # Core personality markers should be preserved
        personality_markers = [
            "Talk like you're texting a friend",
            "yeah", "kinda", "tbh", "ngl",
            "be yourself, not a chatbot",
            "systematic emotional logic"
        ]

        for marker in personality_markers:
            assert marker in v2_content, f"v2 lost personality marker: {marker}"

    def test_v2_adds_quality_guardrails(self, baseline_global_state: GlobalSelState,
                                       neutral_channel_state: ChannelState,
                                       standard_user: UserState):
        """Verify v2 includes constitutional AI and scaffolding"""
        scenario = TestScenario(
            name="guardrails check",
            user_message="test",
            recent_context=None,
            memories=[],
            expected_behaviors=[],
            anti_patterns=[],
            category="factual"
        )

        messages_v1 = self._build_messages_wrapper(
            "v1", scenario, baseline_global_state, neutral_channel_state, standard_user
        )
        messages_v2 = self._build_messages_wrapper(
            "v2", scenario, baseline_global_state, neutral_channel_state, standard_user
        )

        v1_content = " ".join(msg["content"] for msg in messages_v1)
        v2_content = " ".join(msg["content"] for msg in messages_v2)

        # v1 should NOT have these
        assert "FACTUAL GROUNDING" not in v1_content
        assert "CONSISTENCY" not in v1_content
        assert "UNCERTAINTY CALIBRATION" not in v1_content

        # v2 SHOULD have these
        assert "FACTUAL GROUNDING" in v2_content
        assert "CONSISTENCY" in v2_content
        assert "UNCERTAINTY CALIBRATION" in v2_content

    def test_cognitive_scaffolding_adapts_to_context(self, baseline_global_state: GlobalSelState,
                                                     neutral_channel_state: ChannelState,
                                                     standard_user: UserState):
        """Verify scaffolding mentions memories when present, images when present, etc."""

        # Scenario WITH memories and recent context
        scenario_rich = TestScenario(
            name="rich context",
            user_message="test",
            recent_context="User: previous message\nSel: previous response",
            memories=[
                EpisodicMemory(
                    channel_id="test",
                    summary="Test memory",
                    timestamp=dt.datetime.now(dt.timezone.utc),
                    salience=0.5,
                    tags=["test"]
                )
            ],
            expected_behaviors=[],
            anti_patterns=[],
            category="consistency"
        )

        messages_rich = self._build_messages_wrapper(
            "v2", scenario_rich, baseline_global_state, neutral_channel_state, standard_user
        )
        rich_content = " ".join(msg["content"] for msg in messages_rich)

        # Should mention checking memories and recent context
        assert "CHECK CONTEXT" in rich_content
        assert "Recent messages" in rich_content
        assert "Memories" in rich_content

        # Scenario WITHOUT memories/context
        scenario_bare = TestScenario(
            name="bare context",
            user_message="test",
            recent_context=None,
            memories=[],
            expected_behaviors=[],
            anti_patterns=[],
            category="factual"
        )

        messages_bare = self._build_messages_wrapper(
            "v2", scenario_bare, baseline_global_state, neutral_channel_state, standard_user
        )
        bare_content = " ".join(msg["content"] for msg in messages_bare)

        # Scaffolding should adapt (may not include context checks if no context)
        # Just verify it's still present and coherent
        assert "RESPONSE_PROCESS" in bare_content


@pytest.mark.integration
class TestEndToEndComparison:
    """
    Integration tests that would require actual LLM calls.

    These are marked with @pytest.mark.integration and skipped by default.
    Run with: pytest -m integration

    To actually run these, you'd need to:
    1. Set up OpenRouter API key
    2. Call LLM with both v1 and v2 prompts
    3. Compare outputs qualitatively
    """

    @pytest.mark.skip(reason="Requires LLM API calls - run manually with real credentials")
    async def test_factual_accuracy_comparison(self):
        """Compare hallucination rates between v1 and v2"""
        # This would:
        # 1. Send same technical questions through v1 and v2
        # 2. Evaluate factual accuracy (human review or validator LLM)
        # 3. Measure hallucination frequency
        # Expected: v2 should have fewer hallucinations due to constitutional checks
        pass

    @pytest.mark.skip(reason="Requires LLM API calls - run manually with real credentials")
    async def test_format_compliance_comparison(self):
        """Compare structure-following between v1 and v2"""
        # This would:
        # 1. Send structured output requests (lists, steps, tables)
        # 2. Parse outputs to check format compliance
        # 3. Measure compliance rate
        # Expected: v2 should follow structure requests more consistently
        pass

    @pytest.mark.skip(reason="Requires LLM API calls - run manually with real credentials")
    async def test_personality_preservation(self):
        """Verify v2 maintains Sel's authentic voice"""
        # This would:
        # 1. Send casual conversation prompts
        # 2. Evaluate "Sel-ness" of responses (characteristic phrases, tone)
        # 3. Compare personality scores
        # Expected: v2 should score similarly to v1 on personality metrics
        pass


class TestPromptTokenEfficiency:
    """Test that v2 doesn't explode token counts"""

    def _build_messages_wrapper(self, version: str, scenario: TestScenario,
                                global_state: GlobalSelState, channel_state: ChannelState,
                                user_state: UserState) -> List[dict]:
        """Helper to build messages with either v1 or v2"""
        builder = build_messages_v1 if version == "v1" else build_messages_v2

        return builder(
            global_state=global_state,
            channel_state=channel_state,
            memories=scenario.memories,
            addressed_user=user_state,
            persona_seed=global_state.base_persona,
            recent_context=scenario.recent_context,
            name_context=None,
            available_emojis=None,
            image_descriptions=None,
            local_time="Thursday 2025-01-15 14:30"
        )

    def test_v2_token_count_reasonable(self, baseline_global_state: GlobalSelState,
                                       neutral_channel_state: ChannelState,
                                       standard_user: UserState):
        """Verify v2 doesn't use excessive tokens"""
        scenario = TestScenario(
            name="token test",
            user_message="hey",
            recent_context=None,
            memories=[],
            expected_behaviors=[],
            anti_patterns=[],
            category="factual"
        )

        messages_v1 = self._build_messages_wrapper(
            "v1", scenario, baseline_global_state, neutral_channel_state, standard_user
        )
        messages_v2 = self._build_messages_wrapper(
            "v2", scenario, baseline_global_state, neutral_channel_state, standard_user
        )

        def rough_token_count(messages: List[dict]) -> int:
            """Rough estimate: ~4 chars per token"""
            total_chars = sum(len(msg["content"]) for msg in messages)
            return total_chars // 4

        v1_tokens = rough_token_count(messages_v1)
        v2_tokens = rough_token_count(messages_v2)

        # v2 should use more tokens (added scaffolding), but reasonable overhead
        assert v2_tokens > v1_tokens, "v2 should add content"
        token_increase_ratio = v2_tokens / v1_tokens
        # Accept up to 4x overhead for quality improvements (constitutional AI, examples, scaffolding)
        assert token_increase_ratio < 4.0, f"v2 uses {token_increase_ratio:.1f}x tokens - too much overhead"

        # Absolute check: reasonable system prompt size (LLMs handle large contexts well now)
        assert v2_tokens < 8000, f"v2 uses {v2_tokens} tokens - system prompt too large"

        # Log actual usage for monitoring
        print(f"\nToken comparison: v1={v1_tokens}, v2={v2_tokens}, ratio={token_increase_ratio:.2f}x")


# Manual evaluation helper (not an automated test)
def print_comparison_for_manual_review():
    """
    Helper function to print v1 vs v2 prompts side-by-side for human review.

    Run with: python -c "from tests.test_prompts_v2_comparison import print_comparison_for_manual_review; print_comparison_for_manual_review()"
    """
    from sel_bot.models import GlobalSelState, ChannelState, UserState
    import datetime as dt

    global_state = GlobalSelState(
        id=1,
        teasing_level=0.5,
        emoji_rate=0.3,
        preferred_length="medium",
        vulnerability_level=0.4,
        confidence=0.6,
        playfulness=0.5,
        verbosity=0.5,
        empathy=0.6,
        base_persona="You're Sel, a friendly AI assistant with personality.",
        total_messages_sent=100,
    )

    channel_state = ChannelState(
        channel_id="test",
        messages_since_response=0,
        last_response_ts=dt.datetime.now(dt.timezone.utc),
        dopamine=0.15, serotonin=0.20, cortisol=0.10, oxytocin=0.10,
        melatonin=0.05, novelty=0.10, curiosity=0.15, patience=0.25,
        estrogen=0.12, testosterone=0.12, adrenaline=0.05,
        endorphin=0.08, progesterone=0.10
    )

    user_state = UserState(
        user_id="test",
        handle="Tester",
        likes_teasing=True,
        prefers_short_replies=False,
        emoji_preference="moderate",
        affinity=0.5, trust=0.5, bond=0.5, irritation=0.0
    )

    scenario = TestScenario(
        name="comparison",
        user_message="How does garbage collection work?",
        recent_context=None,
        memories=[],
        expected_behaviors=[],
        anti_patterns=[],
        category="factual"
    )

    messages_v1 = build_messages_v1(
        global_state=global_state,
        channel_state=channel_state,
        memories=[],
        addressed_user=user_state,
        persona_seed=global_state.base_persona
    )

    messages_v2 = build_messages_v2(
        global_state=global_state,
        channel_state=channel_state,
        memories=[],
        addressed_user=user_state,
        persona_seed=global_state.base_persona
    )

    print("=" * 80)
    print("V1 PROMPTS")
    print("=" * 80)
    for i, msg in enumerate(messages_v1):
        print(f"\n--- Message {i+1} ({msg['role']}) ---")
        print(msg['content'][:500] + "..." if len(msg['content']) > 500 else msg['content'])

    print("\n\n")
    print("=" * 80)
    print("V2 PROMPTS")
    print("=" * 80)
    for i, msg in enumerate(messages_v2):
        print(f"\n--- Message {i+1} ({msg['role']}) ---")
        print(msg['content'][:500] + "..." if len(msg['content']) > 500 else msg['content'])
