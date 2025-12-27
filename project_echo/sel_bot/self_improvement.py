"""Bounded self-improvement helpers for Sel."""

from __future__ import annotations

import json
import logging
from typing import Dict, List, Optional

from .llm_client import OpenRouterClient
from .models import GlobalSelState, ImprovementSuggestion, SelfTuningEvent
from .state_manager import StateManager


logger = logging.getLogger(__name__)


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


class SelfImprovementManager:
    """Applies bounded persona/config tweaks and records suggestions."""

    def __init__(
        self,
        state_manager: StateManager,
        llm_client: OpenRouterClient,
        *,
        max_step: float = 0.12,
        max_persona_length: int = 600,
        max_keywords: int = 16,
    ) -> None:
        self.state_manager = state_manager
        self.llm_client = llm_client
        self.max_step = max_step
        self.max_persona_length = max_persona_length
        self.max_keywords = max_keywords

    async def apply_bounded_adjustments(
        self,
        global_state: GlobalSelState,
        *,
        reason: str,
        delta: Dict[str, object],
    ) -> Dict[str, Dict[str, object]]:
        """
        Apply small, logged adjustments to persona/config fields.

        delta accepts numeric steps for sliders, or replacements for persona/keywords.
        All changes are clamped and recorded in SelfTuningEvent.
        """

        changes: Dict[str, Dict[str, object]] = {}

        for field, value in delta.items():
            if field in {
                "teasing_level",
                "emoji_rate",
                "vulnerability_level",
                "confidence",
                "playfulness",
                "verbosity",
                "empathy",
            }:
                try:
                    step = float(value)
                except Exception:
                    continue
                step = max(-self.max_step, min(self.max_step, step))
                current = getattr(global_state, field)
                new_value = _clamp(current + step)
                if new_value == current:
                    continue
                setattr(global_state, field, new_value)
                changes[field] = {"from": current, "to": new_value, "step": step}
            elif field == "preferred_length":
                if not isinstance(value, str):
                    continue
                clean = value.strip().lower()
                if clean not in {"short", "medium", "long"}:
                    continue
                current = global_state.preferred_length
                if current == clean:
                    continue
                global_state.preferred_length = clean
                changes[field] = {"from": current, "to": clean}
            elif field == "base_persona":
                if not isinstance(value, str):
                    continue
                trimmed = value.strip()
                if not trimmed:
                    continue
                trimmed = trimmed[: self.max_persona_length]
                current = global_state.base_persona
                if current == trimmed:
                    continue
                global_state.base_persona = trimmed
                changes[field] = {"from": current[:80], "to": trimmed[:80]}
            elif field == "continuation_keywords":
                if not isinstance(value, list):
                    continue
                keywords: List[str] = []
                for kw in value[: self.max_keywords]:
                    if not isinstance(kw, str):
                        continue
                    clean_kw = kw.strip().lower()
                    if not clean_kw:
                        continue
                    if len(clean_kw) > 32:
                        clean_kw = clean_kw[:32]
                    if clean_kw not in keywords:
                        keywords.append(clean_kw)
                if not keywords:
                    continue
                current = global_state.continuation_keywords or []
                if current == keywords:
                    continue
                global_state.continuation_keywords = keywords
                changes[field] = {"from": current, "to": keywords}

        if not changes:
            return changes

        async with self.state_manager.session() as session:
            session.add(SelfTuningEvent(reason=reason[:255], changes=changes, applied=True))
            await session.merge(global_state)
            await session.commit()
        return changes

    async def generate_suggestions(
        self, *, context: str, proposed_by: Optional[str] = None
    ) -> List[ImprovementSuggestion]:
        """Ask the utility model for structured improvement suggestions and persist them."""

        try:
            suggestions_json = await self.llm_client.generate_self_improvement_suggestions(context)
        except Exception as exc:
            logger.warning("Self-improvement suggestion call failed: %s", exc)
            suggestions_json = []

        parsed: List[Dict[str, str]] = []
        if isinstance(suggestions_json, list):
            parsed = [s for s in suggestions_json if isinstance(s, dict)]

        stored: List[ImprovementSuggestion] = []
        async with self.state_manager.session() as session:
            for item in parsed[:5]:
                summary = str(item.get("title") or item.get("summary") or "Untitled suggestion")
                details = str(item.get("detail") or item.get("details") or json.dumps(item))
                category = str(item.get("category") or "config")
                suggestion = ImprovementSuggestion(
                    summary=summary[:255],
                    details=details,
                    category=category[:64],
                    status="pending",
                    proposed_by=proposed_by,
                    context=context,
                )
                session.add(suggestion)
                stored.append(suggestion)
            await session.commit()
            for suggestion in stored:
                await session.refresh(suggestion)
        return stored
