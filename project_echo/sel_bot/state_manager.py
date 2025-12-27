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
            result = await session.execute(select(GlobalSelState))
            state = result.scalar_one_or_none()
            if state is None:
                state = GlobalSelState(
                    base_persona=self.persona_seed or GlobalSelState().base_persona,
                    continuation_keywords=list(self.default_continuation_keywords),
                )
                session.add(state)
                await session.commit()
                await session.refresh(state)
            elif not getattr(state, "continuation_keywords", None) and self.default_continuation_keywords:
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
    ) -> FeedbackEvent:
        async with self.session() as session:
            event = FeedbackEvent(
                sel_message_id=sel_message_id,
                channel_id=channel_id,
                user_id=user_id,
                latency_ms=latency_ms,
                sentiment=sentiment,
            )
            session.add(event)
            await session.commit()
            await session.refresh(event)
            return event
