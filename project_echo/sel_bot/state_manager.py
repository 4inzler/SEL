"""
Helpers for loading and persisting Sel's state in the database.
"""

from __future__ import annotations

from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .models import ChannelState, EpisodicMemory, FeedbackEvent, GlobalSelState, UserState


class StateManager:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        persona_seed: str = "",
        continuation_keywords: Optional[list[str]] = None,
    ) -> None:
        self.session_factory = session_factory
        self.persona_seed = persona_seed
        self.default_continuation_keywords = continuation_keywords or []

    def session(self) -> AsyncSession:
        return self.session_factory()

    async def ensure_global_state(self) -> GlobalSelState:
        async with self.session() as session:
            result = await session.execute(select(GlobalSelState).order_by(GlobalSelState.id.asc()))
            states = list(result.scalars().all())
            state = states[0] if states else None

            if state is None:
                state = GlobalSelState(
                    base_persona=self.persona_seed or GlobalSelState().base_persona,
                    continuation_keywords=list(self.default_continuation_keywords),
                )
                session.add(state)
                await session.commit()
                await session.refresh(state)
                return state

            # Cleanup: ensure single global row
            if len(states) > 1:
                for extra in states[1:]:
                    await session.delete(extra)
                await session.commit()
                await session.refresh(state)

            if not getattr(state, "continuation_keywords", None) and self.default_continuation_keywords:
                state.continuation_keywords = list(self.default_continuation_keywords)
                await session.merge(state)
                await session.commit()
                await session.refresh(state)
            return state

    async def get_channel_state(self, channel_id: str) -> ChannelState:
        async with self.session() as session:
            state = await session.get(ChannelState, channel_id)
            if state is None:
                state = ChannelState(channel_id=channel_id)
                session.add(state)
                await session.commit()
                await session.refresh(state)
            return state

    async def update_channel_state(self, state: ChannelState) -> ChannelState:
        async with self.session() as session:
            persisted = await session.merge(state)
            await session.commit()
            return persisted

    async def get_user_state(self, user_id: str, handle: str) -> UserState:
        async with self.session() as session:
            state = await session.get(UserState, user_id)
            if state is None:
                state = UserState(user_id=user_id, handle=handle)
                session.add(state)
                await session.commit()
                await session.refresh(state)
            elif state.handle != handle:
                state.handle = handle
                await session.commit()
            return state

    async def add_memory(
        self,
        channel_id: str,
        summary: str,
        tags: Optional[Iterable[str]] = None,
        embedding=None,
        salience: float = 0.5,
    ) -> EpisodicMemory:
        async with self.session() as session:
            memory = EpisodicMemory(
                channel_id=channel_id,
                summary=summary,
                tags=list(tags or []),
                embedding=embedding,
                salience=salience,
            )
            session.add(memory)
            await session.commit()
            await session.refresh(memory)
            return memory

    async def list_memories(self, channel_id: str, limit: int = 50) -> list[EpisodicMemory]:
        async with self.session() as session:
            result = await session.execute(
                select(EpisodicMemory)
                .where(EpisodicMemory.channel_id == channel_id)
                .order_by(EpisodicMemory.timestamp.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

    async def log_feedback(
        self,
        sel_message_id: str,
        channel_id: str,
        user_id: Optional[str],
        latency_ms: int,
        sentiment: str,
        confidence_score: Optional[int] = None,
    ) -> FeedbackEvent:
        async with self.session() as session:
            event = FeedbackEvent(
                sel_message_id=sel_message_id,
                channel_id=channel_id,
                user_id=user_id,
                latency_ms=latency_ms,
                sentiment=sentiment,
                confidence_score=confidence_score,
            )
            session.add(event)
            await session.commit()
            await session.refresh(event)
            return event

    async def list_confidence_scores(self, limit: int = 200) -> list[int]:
        """Return recent confidence scores (most recent last) across all channels."""
        async with self.session() as session:
            result = await session.execute(
                select(FeedbackEvent.confidence_score)
                .where(FeedbackEvent.confidence_score.is_not(None))
                .order_by(FeedbackEvent.created_at.desc())
                .limit(limit)
            )
            scores = [row[0] for row in result.fetchall() if row[0] is not None]
            return list(reversed(scores))
