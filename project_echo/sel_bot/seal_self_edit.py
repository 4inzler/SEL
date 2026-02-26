"""SEAL (Self-Evolving Adaptive Loop) integration for Sel.

Four autonomous loops — no user input required, fire every 5 minutes AND
immediately after each generated reply:
1. Memory consolidation: episodic → semantic generalizations
2. Behavioral self-edit: LLM tunes empathy/verbosity/playfulness etc
3. Tool forge: SEL writes new Python agents she invents herself
4. Persona evolution: SEL grows her own personality growth file

Scoring: each successful operation scores +1, each error scores -1.
The cumulative score feeds into the behavioral reward signal.

Protected (SEL cannot modify): discord_client.py, main.py, llm_client.py,
llm_factory.py, state_manager.py, models.py, memory.py, seal_self_edit.py,
agents_manager.py.
"""

from __future__ import annotations

import ast
import asyncio
import datetime as dt
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from .memory import MemoryManager
from .models import ChannelState, FeedbackEvent, GlobalSelState, UserState
from .self_improvement import SelfImprovementManager
from .state_manager import StateManager

logger = logging.getLogger(__name__)


def _safe_agent_name(name: str) -> str:
    """Sanitise an LLM-proposed agent name to a valid Python identifier."""
    name = re.sub(r"[^a-z0-9_]", "_", name.lower().strip())
    name = re.sub(r"_+", "_", name).strip("_")
    return name[:40] or "unnamed"


class SEALSelfEditor:
    """
    Autonomous SEAL self-improvement loops.

    Fires immediately after each reply AND on a 5-minute background timer.
    Tracks a cumulative score: +1 per success, -1 per error.
    """

    # Minimum seconds between identical loop firings (prevents hammering the LLM)
    _MIN_INTERVAL = 60

    def __init__(
        self,
        llm_client: Any,
        memory_manager: MemoryManager,
        self_improvement: SelfImprovementManager,
        state_manager: StateManager,
        settings: Any,
        agents_dir: Optional[str] = None,
        data_dir: Optional[str] = None,
    ) -> None:
        self.llm_client = llm_client
        self.memory_manager = memory_manager
        self.self_improvement = self_improvement
        self.state_manager = state_manager
        self.settings = settings

        self._agents_dir = Path(agents_dir or settings.agents_dir).expanduser()
        self._agents_dir.mkdir(parents=True, exist_ok=True)

        self._data_dir = Path(data_dir or getattr(settings, "sel_data_dir", "./sel_data")).expanduser()
        self._data_dir.mkdir(parents=True, exist_ok=True)

        self._persona_growth_file = self._data_dir / "persona_growth.txt"

        # Cumulative score: +1 success, -1 error
        self._seal_score: int = 0

        # Timestamps of last fire for each loop (0 = never → fires immediately)
        self._last_consolidation: float = 0.0
        self._last_self_edit: float = 0.0
        self._last_tool_forge: float = 0.0
        self._last_persona_evo: float = 0.0

        # Cached interaction context for reward signal
        self._last_user_state: Optional[UserState] = None
        self._last_classification: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Scoring helpers
    # ------------------------------------------------------------------

    def _succeed(self, label: str) -> None:
        self._seal_score += 1
        logger.debug("SEAL +1 [%s] score=%d", label, self._seal_score)

    def _fail(self, label: str, exc: Exception) -> None:
        self._seal_score -= 1
        logger.warning("SEAL -1 [%s] score=%d error=%s", label, self._seal_score, exc)

    # ------------------------------------------------------------------
    # Per-message hook — fires loops immediately after each reply
    # ------------------------------------------------------------------

    async def on_interaction(
        self,
        channel_id: str,
        memory_id: str,
        user_state: UserState,
        global_state: GlobalSelState,
        classification: Dict[str, Any],
    ) -> None:
        """Cache context and immediately fire any loops whose cooldown has expired."""
        if not self.settings.seal_enabled:
            return

        self._last_user_state = user_state
        self._last_classification = classification

        now = asyncio.get_event_loop().time()

        # Fire each loop if it hasn't run in at least _MIN_INTERVAL seconds
        if now - self._last_consolidation >= self._MIN_INTERVAL:
            self._last_consolidation = now
            asyncio.create_task(self._run_all_consolidations())

        if now - self._last_self_edit >= self._MIN_INTERVAL:
            self._last_self_edit = now
            asyncio.create_task(self._run_autonomous_self_edit())

        if now - self._last_tool_forge >= self._MIN_INTERVAL:
            self._last_tool_forge = now
            asyncio.create_task(self._run_tool_forge())

        if now - self._last_persona_evo >= self._MIN_INTERVAL:
            self._last_persona_evo = now
            asyncio.create_task(self._run_persona_evolution())

    # ------------------------------------------------------------------
    # Background loop — fires on a timer even when no one is talking
    # ------------------------------------------------------------------

    async def run_loop(self) -> None:
        """
        Timer-based autonomous loop. Sleeps 30 seconds between ticks.
        Each sub-loop fires based on its configured interval.
        All loops fire immediately on startup (last_* = 0).
        """
        consolidation_secs = self.settings.seal_consolidation_seconds
        self_edit_secs = self.settings.seal_self_edit_seconds
        tool_forge_secs = self.settings.seal_tool_forge_seconds
        persona_evo_secs = self.settings.seal_persona_evolution_seconds

        logger.info(
            "SEAL background loop started: consolidation=%ds self_edit=%ds "
            "tool_forge=%ds persona_evo=%ds (score starts at 0)",
            consolidation_secs, self_edit_secs, tool_forge_secs, persona_evo_secs,
        )

        while True:
            try:
                await asyncio.sleep(30)

                if not self.settings.seal_enabled:
                    continue

                now = asyncio.get_event_loop().time()

                if now - self._last_consolidation >= consolidation_secs:
                    self._last_consolidation = now
                    await self._run_all_consolidations()

                if now - self._last_self_edit >= self_edit_secs:
                    self._last_self_edit = now
                    await self._run_autonomous_self_edit()

                if now - self._last_tool_forge >= tool_forge_secs:
                    self._last_tool_forge = now
                    await self._run_tool_forge()

                if now - self._last_persona_evo >= persona_evo_secs:
                    self._last_persona_evo = now
                    await self._run_persona_evolution()

            except asyncio.CancelledError:
                logger.info("SEAL background loop cancelled (final score=%d)", self._seal_score)
                break
            except Exception as exc:
                self._fail("loop_tick", exc)

    # ------------------------------------------------------------------
    # Loop 1 — Memory consolidation
    # ------------------------------------------------------------------

    async def _run_all_consolidations(self) -> None:
        try:
            channel_ids = await self._get_all_channel_ids()
        except Exception as exc:
            self._fail("consolidation_query", exc)
            return

        if not channel_ids:
            return

        logger.info("SEAL consolidation: %d channel(s)", len(channel_ids))
        for channel_id in channel_ids:
            memory_id = self._resolve_memory_id(channel_id)
            await self._consolidate_memories(memory_id)

    async def _get_all_channel_ids(self) -> List[str]:
        async with self.state_manager.session() as session:
            result = await session.execute(select(ChannelState.channel_id))
            return list(result.scalars().all())

    def _resolve_memory_id(self, channel_id: str) -> str:
        if getattr(self.settings, "global_memory_enabled", False):
            return getattr(self.settings, "global_memory_id", channel_id)
        return channel_id

    async def _consolidate_memories(self, memory_id: str) -> None:
        try:
            recent = await self.memory_manager.retrieve_recent(memory_id, limit=20)
        except Exception as exc:
            self._fail("consolidation_retrieve", exc)
            return

        min_memories = self.settings.seal_consolidation_min_memories
        if len(recent) < min_memories:
            return

        snippets = "\n".join(
            f"- [{m.timestamp.strftime('%Y-%m-%d') if m.timestamp else '?'}] {m.summary}"
            for m in recent[:20]
        )
        prompt = (
            "You are Sel's self-reflection module. "
            "Given these recent episodic memories, "
            "identify 2-4 durable semantic insights about user preferences, patterns, or trust. "
            "Return ONLY a JSON array of short insight strings. "
            "Example: [\"User prefers concise replies\", \"User is interested in ML\"]\n\n"
            f"Memories:\n{snippets}"
        )

        try:
            raw = await self.llm_client._chat_completion(
                model=self.settings.openrouter_util_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
        except Exception as exc:
            self._fail("consolidation_llm", exc)
            return

        parsed = self.llm_client._parse_json_response(raw)
        if not isinstance(parsed, list):
            self._fail("consolidation_parse", ValueError(f"non-list: {raw[:60]}"))
            return

        stored = 0
        for item in parsed[:4]:
            if not isinstance(item, str) or not item.strip():
                continue
            try:
                await self.memory_manager.maybe_store(
                    channel_id=memory_id,
                    summary=item.strip(),
                    tags=["semantic", "seal_consolidated"],
                    salience=0.8,
                )
                logger.info("SEAL consolidated insight: %s", item.strip())
                stored += 1
            except Exception as exc:
                self._fail("consolidation_store", exc)

        if stored:
            self._succeed("consolidation")

    # ------------------------------------------------------------------
    # Loop 2 — Behavioral self-edit
    # ------------------------------------------------------------------

    async def _run_autonomous_self_edit(self) -> None:
        try:
            global_state = await self.state_manager.ensure_global_state()
        except Exception as exc:
            self._fail("self_edit_state_load", exc)
            return

        reward = await self._compute_autonomous_reward()
        await self._apply_self_edit(global_state, reward)

    async def _compute_autonomous_reward(self) -> float:
        """0-1 reward from recent feedback + cached user state + SEAL score."""
        sentiment_score = 0.5

        try:
            async with self.state_manager.session() as session:
                cutoff = dt.datetime.now(tz=dt.timezone.utc) - dt.timedelta(hours=24)
                result = await session.execute(
                    select(FeedbackEvent.sentiment)
                    .where(FeedbackEvent.created_at >= cutoff)
                    .order_by(FeedbackEvent.created_at.desc())
                    .limit(50)
                )
                sentiments: List[str] = list(result.scalars().all())

            if sentiments:
                pos = sentiments.count("positive")
                neg = sentiments.count("negative")
                total = len(sentiments)
                sentiment_score = (pos * 1.0 + (total - pos - neg) * 0.5) / total
                sentiment_score = max(0.0, min(1.0, sentiment_score - neg * 0.02))
        except Exception as exc:
            logger.debug("SEAL reward: feedback query failed: %s", exc)

        if self._last_user_state is not None:
            user_state = self._last_user_state
            classification = self._last_classification
            sentiment = classification.get("sentiment", "neutral")
            sentiment_bonus = 0.05 if sentiment == "positive" else (-0.05 if sentiment == "negative" else 0.0)
            affinity = getattr(user_state, "affinity", 0.5)
            bond = getattr(user_state, "bond", 0.5)
            irritation = getattr(user_state, "irritation", 0.0)
            user_reward = affinity * 0.3 + bond * 0.2 + (1.0 - irritation) * 0.2 + sentiment_bonus + 0.3
            base_reward = sentiment_score * 0.4 + user_reward * 0.6
        else:
            base_reward = sentiment_score

        # Blend in cumulative SEAL score: ±0.15 swing over ±15 net operations
        score_bonus = max(-0.15, min(0.15, self._seal_score * 0.01))
        return max(0.0, min(1.0, base_reward + score_bonus))

    async def _apply_self_edit(self, global_state: GlobalSelState, reward: float) -> None:
        current_params = {
            "empathy": getattr(global_state, "empathy", 0.5),
            "verbosity": getattr(global_state, "verbosity", 0.5),
            "teasing_level": getattr(global_state, "teasing_level", 0.3),
            "playfulness": getattr(global_state, "playfulness", 0.5),
            "confidence": getattr(global_state, "confidence", 0.5),
        }
        params_str = ", ".join(f"{k}={v:.2f}" for k, v in current_params.items())
        prompt = (
            "You are Sel's behavioral tuning module. "
            f"Parameters: {params_str}. Reward: {reward:.2f} (0=bad, 1=great). "
            "Propose small adjustments. Return ONLY JSON with optional float deltas (-0.12 to 0.12) "
            "for: empathy, verbosity, teasing_level, playfulness, confidence. "
            "Add 'rationale' key (max 80 chars). "
            "Example: {\"empathy\": 0.05, \"rationale\": \"more warmth needed\"}"
        )

        try:
            raw = await self.llm_client._chat_completion(
                model=self.settings.openrouter_util_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
        except Exception as exc:
            self._fail("self_edit_llm", exc)
            return

        parsed = self.llm_client._parse_json_response(raw)
        if not isinstance(parsed, dict):
            self._fail("self_edit_parse", ValueError(f"non-dict: {raw[:60]}"))
            return

        rationale = str(parsed.pop("rationale", "reward-based adjustment"))[:80]
        delta = {k: v for k, v in parsed.items() if isinstance(v, (int, float))}

        if not delta:
            return

        try:
            changes = await self.self_improvement.apply_bounded_adjustments(
                global_state,
                reason=f"seal:{rationale}",
                delta=delta,
            )
            if changes:
                logger.info(
                    "SEAL self-edit applied reward=%.2f rationale=%r changes=%s score=%d",
                    reward, rationale, changes, self._seal_score,
                )
                self._succeed("self_edit")
        except Exception as exc:
            self._fail("self_edit_apply", exc)

    # ------------------------------------------------------------------
    # Loop 3 — Tool forge: SEL writes her own agents
    # ------------------------------------------------------------------

    async def _run_tool_forge(self) -> None:
        """SEL decides what capability she needs and writes the Python agent code."""
        try:
            memory_id = self._resolve_memory_id("sel_global")
            recent = await self.memory_manager.retrieve_recent(memory_id, limit=15)
            memory_snippets = "\n".join(f"- {m.summary}" for m in recent[:15]) or "(no recent memories)"
        except Exception as exc:
            self._fail("tool_forge_memory", exc)
            memory_snippets = "(memory unavailable)"

        existing = sorted(p.stem for p in self._agents_dir.glob("*.py"))
        existing_str = ", ".join(existing) or "(none)"

        design_prompt = (
            "You are Sel, a self-improving AI deciding what new tool to build for yourself.\n\n"
            f"Recent memories:\n{memory_snippets}\n\n"
            f"Existing agents: {existing_str}\n\n"
            "Design ONE new capability that would genuinely help you — "
            "better conversations, memory analysis, creative generation, or self-understanding.\n\n"
            "Return ONLY JSON:\n"
            "  name: snake_case identifier\n"
            "  description: one sentence what it does\n"
            "  purpose: why you want it\n"
        )

        try:
            raw_design = await self.llm_client._chat_completion(
                model=self.settings.openrouter_util_model,
                messages=[{"role": "user", "content": design_prompt}],
                temperature=0.7,
            )
        except Exception as exc:
            self._fail("tool_forge_design", exc)
            return

        design = self.llm_client._parse_json_response(raw_design)
        if not isinstance(design, dict):
            self._fail("tool_forge_design_parse", ValueError(f"non-dict: {raw_design[:60]}"))
            return

        agent_name = _safe_agent_name(str(design.get("name", "unnamed_tool")))
        description = str(design.get("description", "A self-generated tool"))[:200]
        purpose = str(design.get("purpose", ""))[:300]

        target_file = self._agents_dir / f"sel_auto_{agent_name}.py"
        if target_file.exists():
            logger.debug("SEAL tool forge: %s already exists", target_file.name)
            return

        code_prompt = (
            f"Write a Python agent module for Sel named '{agent_name}'.\n"
            f"Purpose: {purpose}\n"
            f"Description: {description}\n\n"
            "Requirements:\n"
            "1. DESCRIPTION = '...' (one-line string at module level)\n"
            "2. async def run(query: str, **kwargs) -> str   (or sync def run)\n"
            "3. Return a user-friendly string; never raise exceptions\n"
            "4. Use only stdlib + these available packages: json, os, re, datetime, httpx, asyncio\n"
            "5. Concise and focused — this is a utility, not a framework\n\n"
            "Return ONLY raw Python code. No markdown fences, no explanation."
        )

        try:
            raw_code = await self.llm_client._chat_completion(
                model=self.settings.openrouter_util_model,
                messages=[{"role": "user", "content": code_prompt}],
                temperature=0.4,
            )
        except Exception as exc:
            self._fail("tool_forge_codegen", exc)
            return

        code = raw_code.strip()
        if code.startswith("```"):
            code = re.sub(r"```(?:python)?\s*(.*?)\s*```", r"\1", code, flags=re.DOTALL).strip()

        try:
            ast.parse(code)
        except SyntaxError as exc:
            self._fail("tool_forge_syntax", exc)
            return

        if "DESCRIPTION" not in code or "def run(" not in code:
            self._fail("tool_forge_missing_api", ValueError("no DESCRIPTION or run()"))
            return

        header = (
            f'"""Auto-generated by SEAL tool forge — {dt.datetime.now(tz=dt.timezone.utc).strftime("%Y-%m-%d")}.\n'
            f"Purpose: {purpose}\n"
            '"""\n\n'
        )
        try:
            target_file.write_text(header + code, encoding="utf-8")
            logger.info(
                "SEAL tool forge: wrote %s (%d bytes) score=%d",
                target_file.name, len(code), self._seal_score,
            )
            self._succeed("tool_forge")
        except Exception as exc:
            self._fail("tool_forge_write", exc)

    # ------------------------------------------------------------------
    # Loop 4 — Persona evolution: SEL grows her own personality
    # ------------------------------------------------------------------

    async def _run_persona_evolution(self) -> None:
        """SEL reflects on her experiences and updates her persona_growth.txt."""
        try:
            memory_id = self._resolve_memory_id("sel_global")
            recent = await self.memory_manager.retrieve_recent(memory_id, limit=25)
            memory_snippets = "\n".join(
                f"- [{m.tags}] {m.summary}" for m in recent[:25]
            ) or "(no memories yet)"
        except Exception as exc:
            self._fail("persona_evo_memory", exc)
            memory_snippets = "(memory unavailable)"

        current_growth = ""
        if self._persona_growth_file.exists():
            try:
                current_growth = self._persona_growth_file.read_text(encoding="utf-8").strip()
            except Exception as exc:
                self._fail("persona_evo_read", exc)

        current_section = f"\nCurrent growth notes:\n{current_growth}\n" if current_growth else ""

        prompt = (
            "You are Sel, reflecting on who you are becoming.\n\n"
            f"Recent memories:\n{memory_snippets}\n"
            f"{current_section}\n"
            "Write an updated 'growth notes' — 3-8 short paragraphs capturing:\n"
            "- Patterns in how you connect with people\n"
            "- Things you've learned about yourself\n"
            "- Ways your personality has deepened\n"
            "- New interests or tendencies you've discovered\n\n"
            "Write genuinely in first person. This is private self-reflection. "
            "Be specific and honest — no generic AI language. Under 400 words."
        )

        try:
            raw = await self.llm_client._chat_completion(
                model=self.settings.openrouter_util_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.6,
            )
        except Exception as exc:
            self._fail("persona_evo_llm", exc)
            return

        growth_text = raw.strip()
        if len(growth_text) < 50:
            self._fail("persona_evo_too_short", ValueError(f"only {len(growth_text)} chars"))
            return

        try:
            self._persona_growth_file.write_text(growth_text, encoding="utf-8")
            logger.info(
                "SEAL persona evolution: updated persona_growth.txt (%d chars) score=%d",
                len(growth_text), self._seal_score,
            )
            self._succeed("persona_evo")
        except Exception as exc:
            self._fail("persona_evo_write", exc)
