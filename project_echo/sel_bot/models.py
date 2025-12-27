"""SQLAlchemy ORM models for Sel's persistent state."""

from __future__ import annotations

import datetime as dt
import logging
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, func, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def create_engine(database_url: str) -> AsyncEngine:
    """
    Create an async SQLAlchemy engine.
    """

    return create_async_engine(database_url, future=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """
    Build an async session factory bound to the engine.
    """

    return async_sessionmaker(engine, expire_on_commit=False)


logger = logging.getLogger(__name__)


class GlobalSelState(Base):
    __tablename__ = "global_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    base_persona: Mapped[str] = mapped_column(
        Text,
        default="You are Sel, a persistent, playful, and adaptive presence in this Discord.",
    )
    teasing_level: Mapped[float] = mapped_column(Float, default=0.3)
    emoji_rate: Mapped[float] = mapped_column(Float, default=0.3)
    preferred_length: Mapped[str] = mapped_column(String(16), default="medium")
    vulnerability_level: Mapped[float] = mapped_column(Float, default=0.4)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    playfulness: Mapped[float] = mapped_column(Float, default=0.5)
    verbosity: Mapped[float] = mapped_column(Float, default=0.5)
    empathy: Mapped[float] = mapped_column(Float, default=0.5)
    randomness: Mapped[float] = mapped_column(Float, default=0.0)
    continuation_keywords: Mapped[List[str]] = mapped_column(JSON, default=list)
    total_messages_sent: Mapped[int] = mapped_column(Integer, default=0)
    positive_reactions_count: Mapped[int] = mapped_column(Integer, default=0)
    negative_reactions_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
    )


class ChannelState(Base):
    __tablename__ = "channel_state"

    channel_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dopamine: Mapped[float] = mapped_column(Float, default=0.0)
    serotonin: Mapped[float] = mapped_column(Float, default=0.0)
    cortisol: Mapped[float] = mapped_column(Float, default=0.0)
    oxytocin: Mapped[float] = mapped_column(Float, default=0.0)
    melatonin: Mapped[float] = mapped_column(Float, default=0.0)
    novelty: Mapped[float] = mapped_column(Float, default=0.0)
    curiosity: Mapped[float] = mapped_column(Float, default=0.0)
    patience: Mapped[float] = mapped_column(Float, default=0.0)
    estrogen: Mapped[float] = mapped_column(Float, default=0.0)
    testosterone: Mapped[float] = mapped_column(Float, default=0.0)
    adrenaline: Mapped[float] = mapped_column(Float, default=0.0)
    endorphin: Mapped[float] = mapped_column(Float, default=0.0)
    progesterone: Mapped[float] = mapped_column(Float, default=0.0)
    focus_topic: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    energy_level: Mapped[float] = mapped_column(Float, default=0.5)
    last_response_ts: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    messages_since_response: Mapped[int] = mapped_column(Integer, default=0)
    last_updated: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
    )
    memories: Mapped[List["EpisodicMemory"]] = relationship(
        back_populates="channel", cascade="all, delete-orphan"
    )


class UserState(Base):
    __tablename__ = "user_state"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    handle: Mapped[str] = mapped_column(String(255))
    last_seen_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_ping_ts: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_channel_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    likes_teasing: Mapped[bool] = mapped_column(default=False)
    prefers_short_replies: Mapped[bool] = mapped_column(default=False)
    emoji_preference: Mapped[str] = mapped_column(String(16), default="medium")
    affinity: Mapped[float] = mapped_column(Float, default=0.5)
    trust: Mapped[float] = mapped_column(Float, default=0.5)
    bond: Mapped[float] = mapped_column(Float, default=0.5)  # Sel's warmth toward the user
    irritation: Mapped[float] = mapped_column(Float, default=0.0)  # Sel's tension toward the user
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
    )


class EpisodicMemory(Base):
    __tablename__ = "episodic_memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[str] = mapped_column(ForeignKey("channel_state.channel_id"))
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    summary: Mapped[str] = mapped_column(Text)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    embedding: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    salience: Mapped[float] = mapped_column(Float, default=0.5)

    channel: Mapped[ChannelState] = relationship(back_populates="memories")


class FeedbackEvent(Base):
    __tablename__ = "feedback_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sel_message_id: Mapped[str] = mapped_column(String(64))
    channel_id: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    sentiment: Mapped[str] = mapped_column(String(16), default="neutral")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=func.now())


class SelfTuningEvent(Base):
    """Log of self-applied bounded adjustments to Sel's persona/config."""

    __tablename__ = "self_tuning_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    reason: Mapped[str] = mapped_column(String(255), default="unspecified")
    changes: Mapped[dict] = mapped_column(JSON, default=dict)
    applied: Mapped[bool] = mapped_column(Boolean, default=True)


class ImprovementSuggestion(Base):
    """Pending improvement ideas requiring human approval."""

    __tablename__ = "improvement_suggestion"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    status: Mapped[str] = mapped_column(String(32), default="pending")
    category: Mapped[str] = mapped_column(String(64), default="config")
    summary: Mapped[str] = mapped_column(String(255))
    details: Mapped[str] = mapped_column(Text)
    proposed_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    applied_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


async def ensure_schema(engine: AsyncEngine) -> None:
    """
    Lightweight schema guard to keep older databases compatible when new columns are added.
    We intentionally avoid a full migration framework and instead patch missing columns in place.
    """

    async with engine.begin() as conn:
        dialect = engine.dialect.name
        statements: list[str] = []

        if dialect == "sqlite":
            result = await conn.execute(text("PRAGMA table_info(user_state)"))
            existing_cols = {row[1] for row in result}
            if "last_seen_at" not in existing_cols:
                statements.append("ALTER TABLE user_state ADD COLUMN last_seen_at TIMESTAMP")
            if "last_ping_ts" not in existing_cols:
                statements.append("ALTER TABLE user_state ADD COLUMN last_ping_ts TIMESTAMP")
            if "last_channel_id" not in existing_cols:
                statements.append("ALTER TABLE user_state ADD COLUMN last_channel_id VARCHAR(64)")
            result = await conn.execute(text("PRAGMA table_info(channel_state)"))
            channel_cols = {row[1] for row in result}
            if "curiosity" not in channel_cols:
                statements.append("ALTER TABLE channel_state ADD COLUMN curiosity FLOAT DEFAULT 0.0")
            if "patience" not in channel_cols:
                statements.append("ALTER TABLE channel_state ADD COLUMN patience FLOAT DEFAULT 0.0")
            if "estrogen" not in channel_cols:
                statements.append("ALTER TABLE channel_state ADD COLUMN estrogen FLOAT DEFAULT 0.0")
            if "testosterone" not in channel_cols:
                statements.append("ALTER TABLE channel_state ADD COLUMN testosterone FLOAT DEFAULT 0.0")
            if "adrenaline" not in channel_cols:
                statements.append("ALTER TABLE channel_state ADD COLUMN adrenaline FLOAT DEFAULT 0.0")
            if "endorphin" not in channel_cols:
                statements.append("ALTER TABLE channel_state ADD COLUMN endorphin FLOAT DEFAULT 0.0")
            if "progesterone" not in channel_cols:
                statements.append("ALTER TABLE channel_state ADD COLUMN progesterone FLOAT DEFAULT 0.0")
            result = await conn.execute(text("PRAGMA table_info(global_state)"))
            global_cols = {row[1] for row in result}
            if "continuation_keywords" not in global_cols:
                statements.append("ALTER TABLE global_state ADD COLUMN continuation_keywords JSON")
        else:
            # ANSI/PG-compatible syntax with IF NOT EXISTS to avoid errors on upgrades
            statements.extend(
                [
                    "ALTER TABLE user_state ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMP WITH TIME ZONE",
                    "ALTER TABLE user_state ADD COLUMN IF NOT EXISTS last_ping_ts TIMESTAMP WITH TIME ZONE",
                    "ALTER TABLE user_state ADD COLUMN IF NOT EXISTS last_channel_id VARCHAR(64)",
                    "ALTER TABLE channel_state ADD COLUMN IF NOT EXISTS curiosity DOUBLE PRECISION DEFAULT 0.0",
                    "ALTER TABLE channel_state ADD COLUMN IF NOT EXISTS patience DOUBLE PRECISION DEFAULT 0.0",
                    "ALTER TABLE channel_state ADD COLUMN IF NOT EXISTS estrogen DOUBLE PRECISION DEFAULT 0.0",
                    "ALTER TABLE channel_state ADD COLUMN IF NOT EXISTS testosterone DOUBLE PRECISION DEFAULT 0.0",
                    "ALTER TABLE channel_state ADD COLUMN IF NOT EXISTS adrenaline DOUBLE PRECISION DEFAULT 0.0",
                    "ALTER TABLE channel_state ADD COLUMN IF NOT EXISTS endorphin DOUBLE PRECISION DEFAULT 0.0",
                    "ALTER TABLE channel_state ADD COLUMN IF NOT EXISTS progesterone DOUBLE PRECISION DEFAULT 0.0",
                    "ALTER TABLE global_state ADD COLUMN IF NOT EXISTS continuation_keywords JSONB",
                ]
            )

        for stmt in statements:
            try:
                await conn.execute(text(stmt))
            except Exception as exc:
                logger.warning("Schema patch failed for statement %s: %s", stmt, exc)
