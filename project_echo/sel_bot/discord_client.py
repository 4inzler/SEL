"""
Discord client handling message events and orchestrating Sel's logic.
"""

from __future__ import annotations

import asyncio
import logging
import time
import re
from collections import Counter
from typing import Optional

import discord
from discord import app_commands
import zoneinfo
from sqlalchemy import select
import datetime as dt
import httpx

from .behaviour import is_direct_question_to_sel, should_respond
from .config import Settings
from .feedback import apply_feedback
from .hormones import (
    HormoneVector,
    apply_message_effects,
    decay_channel_hormones,
    apply_silence_drift,
    temperature_for_hormones,
)
from .llm_client import OpenRouterClient
from .memory import MemoryManager
from .models import ChannelState, GlobalSelState, UserState
from .prompts import build_messages as build_messages_v1, derive_style_guidance, format_style_hint
from .prompts_v2 import build_messages_v2
from .self_improvement import SelfImprovementManager
from .state_manager import StateManager
from .agents_manager import AgentsManager

logger = logging.getLogger(__name__)


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _extract_opener(text: str, max_words: int = 4) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    cleaned = cleaned.replace("\n", " ")
    cleaned = re.sub(r"^[@#][A-Za-z0-9_]+\s*", "", cleaned)
    cleaned = re.sub(r"^[\"'`\(\[]+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    words = re.findall(r"[A-Za-z0-9']+", cleaned.lower())
    if not words:
        return ""
    return " ".join(words[:max_words])


def _name_called(lowered_content: str, bot_name: str) -> bool:
    if not lowered_content:
        return False
    name = (bot_name or "").strip().lower()
    if not name:
        return False
    pattern = rf"\b{re.escape(name)}\b"
    return re.search(pattern, lowered_content) is not None


def _safe_to_split_reply(text: str) -> bool:
    if "```" in text:
        return False
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("-", "*", "1.", "2.", "3.")):
            return False
    return True


def _split_reply_for_cadence(text: str, max_parts: int = 3) -> list[str]:
    cleaned = (text or "").strip()
    if not cleaned:
        return []
    if not _safe_to_split_reply(cleaned):
        return [cleaned]
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    sentences = [s.strip() for s in sentences if s.strip()]
    if len(sentences) < 3:
        return [cleaned]
    parts_count = 2 if len(sentences) <= 4 else min(max_parts, 3)
    total_len = sum(len(s) for s in sentences)
    target_len = max(1, int(total_len / parts_count))
    parts: list[str] = []
    current: list[str] = []
    current_len = 0
    for sentence in sentences:
        if current and current_len + len(sentence) > target_len and len(parts) < parts_count - 1:
            parts.append(" ".join(current))
            current = [sentence]
            current_len = len(sentence)
        else:
            current.append(sentence)
            current_len += len(sentence)
    if current:
        parts.append(" ".join(current))
    return parts


def _followup_delay(chunk: str, hormones: HormoneVector, index: int) -> float:
    base = 0.35 + min(0.8, (len(chunk) / 200.0) * 0.25)
    mood = 0.2 - (hormones.melatonin * 0.2) + (hormones.adrenaline * 0.1) - (hormones.patience * 0.05)
    return max(0.2, min(1.4, base + mood + (index * 0.05)))


def _extract_topic_keywords(recent_msgs: list[str]) -> list[str]:
    stopwords = {
        "the",
        "and",
        "but",
        "with",
        "that",
        "this",
        "from",
        "you",
        "your",
        "about",
        "just",
        "like",
        "what",
        "when",
        "where",
        "how",
        "why",
        "are",
        "was",
        "were",
        "they",
        "them",
        "their",
        "have",
        "has",
        "had",
        "not",
        "for",
        "lol",
        "lmao",
        "yeah",
        "okay",
        "ok",
        "tbh",
        "ngl",
    }
    counts: Counter[str] = Counter()
    for entry in recent_msgs:
        text = entry.split(":", 1)[1] if ":" in entry else entry
        for token in re.findall(r"[A-Za-z0-9']+", text.lower()):
            if len(token) < 4 or token in stopwords:
                continue
            counts[token] += 1
    return [word for word, _ in counts.most_common(3)]


def _adjust_repeated_opener(reply: str, recent_openers: list[str]) -> str:
    if not reply or not recent_openers:
        return reply
    opener = _extract_opener(reply)
    if not opener:
        return reply
    recent_set = {o.lower() for o in recent_openers}
    if opener not in recent_set:
        return reply
    for filler in ("yeah", "oh", "hey", "lol", "lmao", "tbh", "ngl", "so", "ok", "okay", "hmm"):
        if reply.lower().startswith(f"{filler} "):
            return reply[len(filler):].lstrip()
    return reply


def _build_channel_dynamics(
    speaker_counts: Counter[str],
    reply_to: str,
    topic_keywords: list[str],
) -> Optional[str]:
    if len(speaker_counts) < 2:
        return None
    top_speakers = [name for name, _ in speaker_counts.most_common(4)]
    if reply_to not in top_speakers:
        top_speakers.insert(0, reply_to)
    names = ", ".join(top_speakers[:4])
    topic_hint = ""
    if topic_keywords:
        topic_hint = f"\nRecent topics: {', '.join(topic_keywords)}."
    return (
        f"Recent active speakers: {names}."
        f"{topic_hint}\n"
        f"You're replying to {reply_to}. If you reference someone else, name them so it's clear."
    )


def _match_agent_request(content: str, agent_names: list[str]) -> Optional[tuple[str, str]]:
    lower = content.lower()
    if not agent_names:
        return None
    for name in agent_names:
        key = name.lower()
        if f"agent:{key}" in lower:
            after = lower.split(f"agent:{key}", 1)[1].strip()
            return name, (after or content)
        if f"use {key}" in lower:
            after = lower.split(f"use {key}", 1)[1].strip()
            return name, after or content
        if f"run {key}" in lower:
            after = lower.split(f"run {key}", 1)[1].strip()
            return name, after or content
        if f"{key} agent" in lower:
            after = lower.split(f"{key} agent", 1)[1].strip()
            return name, after or content
        if f"{key} tool" in lower:
            after = lower.split(f"{key} tool", 1)[1].strip()
            return name, after or content
        # Bash agent intent routing
        if key in {"bash_agent", "bash"}:
            if lower.startswith("bash "):
                return name, content.split(" ", 1)[1].strip()
            if lower.startswith("!bash"):
                return name, content.split("!bash", 1)[1].strip()
            if "bash:" in lower:
                return name, content.split("bash:", 1)[1].strip()
            if "run bash" in lower:
                after = lower.split("run bash", 1)[1].strip()
                # recover original slice length
                offset = content.lower().find("run bash") + len("run bash")
                return name, content[offset:].strip() or after
            if "shell command" in lower or "run command" in lower:
                after = lower.split("command", 1)[1].strip()
                offset = content.lower().find("command") + len("command")
                return name, content[offset:].strip() or after
            if "```bash" in lower:
                start = content.lower().find("```bash") + len("```bash")
                end = content.lower().find("```", start)
                snippet = content[start:end] if end != -1 else content[start:]
                return name, snippet.strip()
    return None


def _bash_command_from_keywords(content: str) -> Optional[str]:
    lower = content.lower()
    # Common explicit requests
    if "fastfetch" in lower or "fast fetch" in lower:
        return "fastfetch"
    if lower.startswith("bash "):
        return content.split(" ", 1)[1].strip()
    if "run command" in lower:
        idx = lower.find("run command") + len("run command")
        return content[idx:].strip()


def _is_authorized(user_id: int, allowed_id: Optional[int]) -> bool:
    return allowed_id is None or user_id == allowed_id


class SelDiscordClient(discord.Client):
    def __init__(
        self,
        settings: Settings,
        state_manager: StateManager,
        llm_client: OpenRouterClient,
        memory_manager: MemoryManager,
        agents_manager: AgentsManager,
        hormone_manager=None,  # Optional HormoneStateManager
        **kwargs,
    ):
        intents = kwargs.pop("intents", discord.Intents.default())
        intents.message_content = True
        intents.messages = True
        intents.reactions = True
        super().__init__(intents=intents, **kwargs)

        self.settings = settings
        self.state_manager = state_manager
        self.llm_client = llm_client
        self.memory_manager = memory_manager
        self.agents_manager = agents_manager
        self.hormone_manager = hormone_manager  # HIM-based hormone storage (optional)
        self.self_improvement = SelfImprovementManager(state_manager, llm_client)
        self.decay_task: Optional[asyncio.Task] = None
        self.ping_task: Optional[asyncio.Task] = None
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        self.decay_task = asyncio.create_task(self._decay_loop())
        self.ping_task = asyncio.create_task(self._inactive_ping_loop())
        self.tree.add_command(app_commands.Command(name="sel_status", description="Show Sel's mood and channel state", callback=self._cmd_status))
        self.tree.add_command(app_commands.Command(name="sel_improve", description="Queue self-improvement suggestions", callback=self._cmd_improve))
        self.tree.add_command(app_commands.Command(name="him_status", description="Check HIM API connectivity", callback=self._cmd_him_status))
        self.tree.add_command(app_commands.Command(name="sel_agents", description="List available agents", callback=self._cmd_agents))
        self.tree.add_command(app_commands.Command(name="sel_run_agent", description="Run an agent with text input", callback=self._cmd_run_agent))
        self.tree.add_command(app_commands.Command(name="sel_cache_stats", description="Show LLM response cache statistics", callback=self._cmd_cache_stats))
        self.tree.add_command(app_commands.Command(name="sel_agent_stats", description="Show agent performance statistics", callback=self._cmd_agent_stats))
        try:
            await self.tree.sync()
        except Exception as exc:
            logger.warning("Failed to sync slash commands: %s", exc)

    async def close(self) -> None:
        if self.decay_task:
            self.decay_task.cancel()
        if self.ping_task:
            self.ping_task.cancel()
        await super().close()

    async def _decay_loop(self) -> None:
        """
        Periodically decay hormones for all known channels with circadian rhythms.

        Uses HormoneStateManager (HIM-based) if available, otherwise falls back
        to legacy SQLAlchemy storage.
        """

        while True:
            try:
                # Get local time for circadian rhythm calculations
                try:
                    tz = zoneinfo.ZoneInfo(self.settings.timezone_name)
                    local_now = dt.datetime.now(tz)
                except Exception:
                    local_now = None

                if self.hormone_manager:
                    # HIM-based hormone decay (in-memory cache)
                    now = dt.datetime.now(tz=dt.timezone.utc)
                    async with self.hormone_manager._cache_lock:
                        for channel_id, cached_state in self.hormone_manager._cache.items():
                            # Apply decay to hormone vector
                            cached_state.vector.decay(local_time=local_now)

                            # Apply silence drift if >10 min inactive
                            last_ts = cached_state.last_response_ts
                            if last_ts and last_ts.tzinfo is None:
                                last_ts = last_ts.replace(tzinfo=dt.timezone.utc)
                            seconds_since = (now - last_ts).total_seconds() if last_ts else None

                            if seconds_since and seconds_since > 600:
                                # Apply silence effects (from hormones.py logic)
                                from .hormones import SILENCE_SEROTONIN_DECAY, _clamp as h_clamp
                                cached_state.vector.serotonin = h_clamp(
                                    cached_state.vector.serotonin - SILENCE_SEROTONIN_DECAY
                                )
                                cached_state.vector.melatonin = h_clamp(
                                    cached_state.vector.melatonin + SILENCE_SEROTONIN_DECAY * 0.5
                                )
                                cached_state.vector.curiosity = h_clamp(
                                    cached_state.vector.curiosity + 0.006
                                )
                                cached_state.vector.patience = h_clamp(
                                    cached_state.vector.patience - 0.008
                                )
                                cached_state.vector.estrogen = h_clamp(
                                    cached_state.vector.estrogen - 0.002
                                )
                                cached_state.vector.testosterone = h_clamp(
                                    cached_state.vector.testosterone - 0.003
                                )
                                cached_state.vector.endorphin = h_clamp(
                                    cached_state.vector.endorphin - 0.01
                                )

                            cached_state.dirty = True  # Mark for persistence
                            cached_state.last_updated = now

                    # Global personality drift (still uses state_manager)
                    async with self.state_manager.session() as session:
                        g_state = (await session.execute(select(GlobalSelState))).scalar_one_or_none()
                        if g_state and self.hormone_manager._cache:
                            # Average dopamine across all cached channels
                            dopamine_avg = sum(
                                s.vector.dopamine for s in self.hormone_manager._cache.values()
                            ) / max(1, len(self.hormone_manager._cache))

                            drift = max(0.0, min(0.01, dopamine_avg))
                            g_state.playfulness = min(1.0, g_state.playfulness + drift)
                            g_state.empathy = max(0.0, min(1.0, g_state.empathy + (-drift / 2)))
                            await session.merge(g_state)
                            await session.commit()

                else:
                    # Legacy SQLAlchemy hormone storage
                    async with self.state_manager.session() as session:
                        result = await session.execute(select(ChannelState))
                        channels = result.scalars().all()
                        now = dt.datetime.now(tz=dt.timezone.utc)
                        for state in channels:
                            last_ts = state.last_response_ts
                            if last_ts and last_ts.tzinfo is None:
                                last_ts = last_ts.replace(tzinfo=dt.timezone.utc)
                            seconds_since = (now - last_ts).total_seconds() if last_ts else None
                            decay_channel_hormones(state, local_time=local_now)
                            apply_silence_drift(state, seconds_since)
                            await session.merge(state)
                        g_state = (await session.execute(select(GlobalSelState))).scalar_one_or_none()
                        if g_state:
                            # personality drift slightly toward calmer if low cortisol, more playful with novelty
                            drift = max(0.0, min(0.01, sum(s.dopamine for s in channels) / (len(channels) + 1)))
                            g_state.playfulness = min(1.0, g_state.playfulness + drift)
                            g_state.empathy = max(0.0, min(1.0, g_state.empathy + (-drift / 2)))
                            await session.merge(g_state)
                        await session.commit()
            except Exception as exc:
                logger.exception("Hormone decay loop error: %s", exc)
            await asyncio.sleep(60)

    @staticmethod
    def _humanize_gap(last_seen: dt.datetime | None, now: dt.datetime) -> str:
        if not last_seen:
            return "a while"
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=dt.timezone.utc)
        delta = now - last_seen
        days = delta.days
        hours = int(delta.seconds / 3600)
        if days > 0:
            return f"{days} day{'s' if days != 1 else ''}"
        if hours > 0:
            return f"{hours} hour{'s' if hours != 1 else ''}"
        minutes = int((delta.seconds % 3600) / 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''}"

    async def _inactive_ping_loop(self) -> None:
        """
        Proactively ping users we have not heard from recently to keep Sel present.
        """

        check_interval = max(120, int(self.settings.inactivity_ping_check_seconds))
        while True:
            try:
                await self._send_inactivity_pings()
            except Exception as exc:
                logger.exception("Inactivity ping loop error: %s", exc)
            await asyncio.sleep(check_interval)

    async def _send_inactivity_pings(self) -> None:
        async with self.state_manager.session() as session:
            result = await session.execute(select(UserState))
            users = result.scalars().all()

        now = dt.datetime.now(tz=dt.timezone.utc)
        inactivity_threshold = now - dt.timedelta(hours=float(self.settings.inactivity_ping_hours))
        cooldown = dt.timedelta(hours=float(self.settings.inactivity_ping_cooldown_hours))

        for user in users:
            last_seen = user.last_seen_at
            if last_seen and last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=dt.timezone.utc)
            if last_seen and last_seen > inactivity_threshold:
                continue

            if user.last_ping_ts:
                last_ping = user.last_ping_ts.replace(tzinfo=dt.timezone.utc) if user.last_ping_ts.tzinfo is None else user.last_ping_ts
                if now - last_ping < cooldown:
                    continue

            if not user.last_channel_id:
                continue

            try:
                channel_id = int(user.last_channel_id)
            except (TypeError, ValueError):
                continue
            if not self.settings.is_channel_allowed(channel_id):
                continue

            channel = self.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await self.fetch_channel(channel_id)
                except Exception as exc:
                    logger.warning("Unable to fetch channel %s for inactivity ping to user %s: %s", channel_id, user.user_id, exc)
                    continue

            await self._ping_user(user, channel, last_seen, now)

    async def _ping_user(self, user_state: UserState, channel: discord.abc.Messageable, last_seen: dt.datetime | None, now: dt.datetime) -> None:
        channel_state = await self.state_manager.get_channel_state(str(channel.id))
        global_state = await self.state_manager.ensure_global_state()
        quiet_for = self._humanize_gap(last_seen, now)
        memories = await self.memory_manager.retrieve(str(channel.id), user_state.handle, limit=max(3, self.settings.memory_recall_limit // 2))

        emoji_block = None
        try:
            emoji_block = ", ".join(str(e) for e in (channel.guild.emojis if getattr(channel, "guild", None) else [])[:20]) or None
        except Exception:
            pass

        name_context = (
            f"You have not heard from {user_state.handle} in {quiet_for}. "
            "Send a short, warm ping inviting them to share what they've been up to. "
            "Sound human, not like a system check, and keep it under two sentences."
        )

        # Feature flag: use v2 prompts if enabled for this channel
        build_messages = build_messages_v2 if self.settings.should_use_prompts_v2(str(channel.id)) else build_messages_v1

        system_messages = build_messages(
            global_state=global_state,
            channel_state=channel_state,
            memories=memories,
            addressed_user=user_state,
            persona_seed=global_state.base_persona or self.settings.persona_seed,
            recent_context=None,
            name_context=name_context,
            available_emojis=emoji_block,
            image_descriptions=None,
            local_time=None,
        )
        try:
            hormones = HormoneVector.from_channel(channel_state)
            response_temp = temperature_for_hormones(hormones, self.settings.openrouter_main_temp)
            reply = await self.llm_client.generate_reply(
                system_messages,
                user_content=f"(Proactive ping for {user_state.handle}; last seen {quiet_for} ago.)",
                temperature=response_temp,
            )
        except Exception as exc:
            logger.error("Failed to craft inactivity ping for user=%s: %s", user_state.user_id, exc)
            return

        try:
            async with channel.typing():
                await asyncio.sleep(0.4)
                sent_msg = await channel.send(reply)
        except Exception as exc:
            logger.warning("Failed sending inactivity ping to user=%s channel=%s: %s", user_state.user_id, channel.id, exc)
            return

        channel_state.last_response_ts = now
        channel_state.messages_since_response = 0
        async with self.state_manager.session() as session:
            user_state.last_ping_ts = now
            await session.merge(user_state)
            await session.merge(channel_state)
            global_state.total_messages_sent += 1
            await session.merge(global_state)
            await session.commit()

        logger.info("Sent inactivity ping to user=%s in channel=%s msg_id=%s", user_state.user_id, channel.id, sent_msg.id)

    async def on_ready(self):
        logger.info("Sel connected as %s", self.user)
        try:
            activity = discord.Activity(type=discord.ActivityType.listening, name="for quiet friends")
            await self.change_presence(status=discord.Status.online, activity=activity)
        except Exception as exc:
            logger.warning("Failed to update Sel presence: %s", exc)

    async def on_message(self, message: discord.Message):
        if message.author.bot or not self.settings.is_channel_allowed(message.channel.id):
            return
        if self.user and message.author.id == self.user.id:
            return

        clean_content = (message.content or "").strip()
        lower_content = clean_content.lower()
        logger.info(
            "RX message channel=%s author=%s content=%s",
            message.channel.id,
            message.author,
            clean_content.replace("\n", " ")[:120],
        )

        # Load state
        global_state = await self.state_manager.ensure_global_state()
        channel_state = await self.state_manager.get_channel_state(str(message.channel.id))
        user_state = await self.state_manager.get_user_state(str(message.author.id), message.author.name)
        now = dt.datetime.now(tz=dt.timezone.utc)
        user_state.last_seen_at = now
        user_state.last_channel_id = str(message.channel.id)

        # Track if the user replied directly to Sel (even without a mention)
        is_reply_to_sel = False
        if message.reference:
            resolved = message.reference.resolved or getattr(message.reference, "cached_message", None)
            if resolved and resolved.author and self.user and resolved.author.id == self.user.id:
                is_reply_to_sel = True
            elif message.reference.message_id and self.user:
                try:
                    ref_msg = await message.channel.fetch_message(message.reference.message_id)
                    is_reply_to_sel = ref_msg.author.id == self.user.id
                except Exception:
                    pass

        # Classify message and update hormones
        classification = await self.llm_client.classify_message(clean_content or "")

        if self.hormone_manager:
            # HIM-based hormone storage
            channel_id = str(message.channel.id)
            cached = await self.hormone_manager.get_state(channel_id)
            pre_hormones = cached.vector
            logger.info(
                "Classification channel=%s sentiment=%s intensity=%s playful=%s memory=%s state_before=%s",
                message.channel.id,
                classification.get("sentiment"),
                classification.get("intensity"),
                classification.get("playful"),
                classification.get("memory_write"),
                pre_hormones.natural_language_summary(),
            )

            # Apply message effects to hormone vector
            hormones = apply_message_effects(
                cached.vector,
                sentiment=str(classification.get("sentiment", "neutral")),
                intensity=float(classification.get("intensity", 0.3) or 0.3),
                playful=bool(classification.get("playful", False)),
            )

            # Update HormoneStateManager cache
            await self.hormone_manager.update_state(
                channel_id,
                hormones,
                focus_topic=channel_state.focus_topic,
                energy_level=channel_state.energy_level,
                messages_since_response=channel_state.messages_since_response,
                last_response_ts=channel_state.last_response_ts,
            )
            logger.info(
                "State after message channel=%s mood=%s",
                message.channel.id,
                hormones.natural_language_summary(),
            )
        else:
            # Legacy SQLAlchemy hormone storage
            pre_hormones = HormoneVector.from_channel(channel_state)
            logger.info(
                "Classification channel=%s sentiment=%s intensity=%s playful=%s memory=%s state_before=%s",
                message.channel.id,
                classification.get("sentiment"),
                classification.get("intensity"),
                classification.get("playful"),
                classification.get("memory_write"),
                pre_hormones.natural_language_summary(),
            )
            hormones = HormoneVector.from_channel(channel_state)
            hormones = apply_message_effects(
                hormones,
                sentiment=str(classification.get("sentiment", "neutral")),
                intensity=float(classification.get("intensity", 0.3) or 0.3),
                playful=bool(classification.get("playful", False)),
            )
            hormones.to_channel(channel_state)
            await self.state_manager.update_channel_state(channel_state)
            logger.info(
                "State after message channel=%s mood=%s",
                message.channel.id,
                hormones.natural_language_summary(),
            )

        # Update per-user feelings
        sentiment = str(classification.get("sentiment", "neutral"))
        global_delta: dict[str, float | str | list] = {}
        if sentiment == "positive":
            user_state.affinity = _clamp(user_state.affinity + 0.05)
            user_state.trust = _clamp(user_state.trust + 0.03)
            user_state.bond = _clamp(user_state.bond + 0.05)
            user_state.irritation = _clamp(user_state.irritation - 0.03, 0.0, 1.0)
            global_delta.update({"playfulness": 0.01, "confidence": 0.005})
        elif sentiment == "negative":
            user_state.affinity = _clamp(user_state.affinity - 0.04)
            user_state.trust = _clamp(user_state.trust - 0.05)
            user_state.bond = _clamp(user_state.bond - 0.03)
            user_state.irritation = _clamp(user_state.irritation + 0.05, 0.0, 1.0)
            global_delta.update({"playfulness": -0.01, "empathy": 0.01})
        else:
            user_state.bond = _clamp(user_state.bond + 0.005)

        if global_delta:
            await self.self_improvement.apply_bounded_adjustments(
                global_state,
                reason=f"feedback:{sentiment}",
                delta=global_delta,
            )

        # Optionally write memory
        if classification.get("memory_write"):
            summary = clean_content
            if not summary:
                summary = "User shared an attachment or non-text message."
            summary = summary[:300]
            salience = float(classification.get("intensity", 0.5))
            await self.memory_manager.maybe_store(
                channel_id=str(message.channel.id),
                summary=summary,
                tags=["user_message"],
                salience=salience,
            )
            logger.info("Stored memory channel=%s summary=%s", message.channel.id, summary)

        bot_name = self.user.name if self.user else "sel"
        name_called = _name_called(lower_content, bot_name)
        misnamed = " cel" in lower_content or lower_content.startswith("cel") or "her name is cel" in lower_content
        is_mentioned = (self.user in message.mentions if self.user else False) or is_reply_to_sel
        addressed_to_sel = is_mentioned or name_called
        direct_question = is_direct_question_to_sel(clean_content, bot_name) or (
            "?" in clean_content and (is_reply_to_sel)
        )
        last_ts = channel_state.last_response_ts
        if last_ts and last_ts.tzinfo is None:
            # Backward compatibility: treat stored naive timestamps as UTC
            last_ts = last_ts.replace(tzinfo=dt.timezone.utc)
        seconds_since_response = (now - last_ts).total_seconds() if last_ts else None
        continuation_keywords = (
            global_state.continuation_keywords
            if getattr(global_state, "continuation_keywords", None)
            else self.settings.continuation_keywords
        )
        continuation_hit = any(kw in lower_content for kw in continuation_keywords)
        recent_followup = (
            seconds_since_response is not None
            and seconds_since_response < 360
            and (
                " you" in lower_content
                or lower_content.startswith("you ")
                or lower_content.endswith(" you")
                or " u " in lower_content
            )
        )
        if recent_followup:
            continuation_hit = True
        if is_reply_to_sel:
            continuation_hit = True
            direct_question = direct_question or "?" in clean_content
        if addressed_to_sel:
            continuation_hit = True

        style_guidance = derive_style_guidance(
            global_state=global_state,
            user_state=user_state,
            sentiment=str(classification.get("sentiment", "neutral")),
            intensity=float(classification.get("intensity", 0.3) or 0.3),
            playful=bool(classification.get("playful", False)),
            user_content=clean_content,
            direct_question=direct_question,
        )
        style_hint = format_style_hint(style_guidance)

        agent_match = _match_agent_request(clean_content, [a.name for a in self.agents_manager.list_agents()])
        if agent_match:
            if not _is_authorized(message.author.id, self.settings.approval_user_id):
                logger.info("Agent request denied for user %s", message.author.id)
                return
            agent_name, agent_input = agent_match
            try:
                result = await self.agents_manager.run_agent_async(agent_name, agent_input)
            except Exception as exc:
                result = f"Agent '{agent_name}' failed: {exc}"
            async with message.channel.typing():
                await asyncio.sleep(0.3)
                sent_msg = await message.channel.send(f"[{agent_name}] {result}")

            global_state.total_messages_sent += 1
            channel_state.last_response_ts = now
            channel_state.messages_since_response = 0
            # Remember what Sel just did
            await self.memory_manager.maybe_store(
                channel_id=str(message.channel.id),
                summary=f"Sel ran agent '{agent_name}' with input: {agent_input[:160]}",
                tags=["agent_action", agent_name],
                salience=0.45,
            )
            async with self.state_manager.session() as session:
                await session.merge(global_state)
                await session.merge(channel_state)
                await session.merge(user_state)
                await session.commit()
            await self.state_manager.log_feedback(
                sel_message_id=str(sent_msg.id),
                channel_id=str(message.channel.id),
                user_id=str(message.author.id),
                latency_ms=0,
                sentiment=classification.get("sentiment", "neutral"),
            )
            return

        # Agent routing by authorization (shell/system) - all goes through system_agent
        if _is_authorized(message.author.id, self.settings.approval_user_id):
            # Explicit bash commands: "bash ls", "run command df", "fastfetch"
            quick_bash = _bash_command_from_keywords(clean_content)
            if quick_bash:
                try:
                    result = await self.agents_manager.run_agent_async("system_agent", quick_bash)
                    await self.memory_manager.maybe_store(
                        channel_id=str(message.channel.id),
                        summary=f"Sel ran: {quick_bash[:50]}",
                        tags=["system_action"],
                        salience=0.4,
                    )
                except Exception as exc:
                    result = f"couldn't run that: {exc}"
                async with message.channel.typing():
                    await asyncio.sleep(0.3)
                    # system_agent already formats output nicely
                    sent_msg = await message.channel.send(str(result or "done"))
                global_state.total_messages_sent += 1
                channel_state.last_response_ts = now
                channel_state.messages_since_response = 0
                async with self.state_manager.session() as session:
                    await session.merge(global_state)
                    await session.merge(channel_state)
                    await session.merge(user_state)
                    await session.commit()
                await self.state_manager.log_feedback(
                    sel_message_id=str(sent_msg.id),
                    channel_id=str(message.channel.id),
                    user_id=str(message.author.id),
                    latency_ms=0,
                    sentiment=classification.get("sentiment", "neutral"),
                )
                return

            # Natural language system queries - use system_agent for conversational output
            try:
                shell_intent = await self.llm_client.classify_shell_command(clean_content)
            except Exception:
                shell_intent = None
            if shell_intent and shell_intent.get("intent"):
                # Route to system_agent for natural language handling
                query = clean_content
                try:
                    result = await self.agents_manager.run_agent_async("system_agent", query)
                    await self.memory_manager.maybe_store(
                        channel_id=str(message.channel.id),
                        summary=f"Sel helped with system: {query[:50]}",
                        tags=["system_action"],
                        salience=0.4,
                    )
                except Exception as exc:
                    result = f"hmm something went wrong: {exc}"
                async with message.channel.typing():
                    await asyncio.sleep(0.3)
                    # Send system_agent's conversational response directly
                    sent_msg = await message.channel.send(str(result or "done"))
                global_state.total_messages_sent += 1
                channel_state.last_response_ts = now
                channel_state.messages_since_response = 0
                async with self.state_manager.session() as session:
                    await session.merge(global_state)
                    await session.merge(channel_state)
                    await session.merge(user_state)
                    await session.commit()
                await self.state_manager.log_feedback(
                    sel_message_id=str(sent_msg.id),
                    channel_id=str(message.channel.id),
                    user_id=str(message.author.id),
                    latency_ms=0,
                    sentiment=classification.get("sentiment", "neutral"),
                )
                return

        improvement_request = is_mentioned and (
            "improvement" in lower_content
            or "self-improve" in lower_content
            or "self improve" in lower_content
        )
        if improvement_request:
            suggestions = await self.self_improvement.generate_suggestions(
                context=clean_content or "(no content)",
                proposed_by=message.author.name,
            )
            if suggestions:
                lines = [
                    f"#{s.id} [{s.category}] {s.summary}" for s in suggestions
                ]
                reply = "Queued improvements (pending approval):\n" + "\n".join(lines)
            else:
                reply = "No concrete improvements to queue right now, but the request was noted."
            try:
                async with message.channel.typing():
                    await asyncio.sleep(0.5)
                    sent_msg = await message.channel.send(reply)
            except Exception as exc:
                logger.warning("Failed to send improvement suggestions: %s", exc)
                return

            global_state.total_messages_sent += 1
            channel_state.last_response_ts = now
            channel_state.messages_since_response = 0
            async with self.state_manager.session() as session:
                await session.merge(global_state)
                await session.merge(channel_state)
                await session.merge(user_state)
                await session.commit()
            await self.state_manager.log_feedback(
                sel_message_id=str(sent_msg.id),
                channel_id=str(message.channel.id),
                user_id=str(message.author.id),
                latency_ms=0,
                sentiment=classification.get("sentiment", "neutral"),
            )
            if suggestions:
                await self._dm_approver_suggestions(suggestions, context_preview=clean_content[:160])
            return

        should_reply = should_respond(
            is_mentioned,
            direct_question,
            hormones,
            base_chance=0.24,
            messages_since_response=channel_state.messages_since_response,
            seconds_since_response=seconds_since_response,
            has_image=any(a.content_type and a.content_type.startswith("image/") for a in message.attachments),
            is_continuation=continuation_hit,
        )
        if not should_reply:
            channel_state.messages_since_response += 1
            await self.state_manager.update_channel_state(channel_state)
            async with self.state_manager.session() as session:
                await session.merge(global_state)
                await session.merge(user_state)
                await session.commit()
            logger.info(
                "Decision: silent channel=%s ms_since=%s secs_since=%s cortisol=%.2f melatonin=%.2f novelty=%.2f",
                message.channel.id,
                channel_state.messages_since_response,
                seconds_since_response,
                hormones.cortisol,
                hormones.melatonin,
                hormones.novelty,
            )
            return

        # Recent context window
        recent_msgs = []
        recent_sel_openers: list[str] = []
        speaker_counts: Counter[str] = Counter()
        history_limit = max(8, self.settings.recent_context_limit)
        try:
            async for msg in message.channel.history(limit=history_limit, oldest_first=False):
                if msg.id == message.id:
                    continue
                if msg.author.bot and msg.author != self.user:
                    continue
                snippet = (msg.content or "").strip()
                if snippet:
                    marker = "->" if msg.reference or (msg.mentions and self.user in msg.mentions) else ""
                    recent_msgs.append(f"{msg.author.display_name}{marker}: {snippet}")
                    if self.user and msg.author.id == self.user.id:
                        opener = _extract_opener(snippet)
                        if opener:
                            recent_sel_openers.append(opener)
                    else:
                        speaker_counts[msg.author.display_name] += 1
        except Exception as exc:
            logger.warning("Failed to fetch recent history for channel %s: %s", message.channel.id, exc)
        recent_context = "\n".join(reversed(recent_msgs))
        topic_keywords = _extract_topic_keywords(recent_msgs)
        speaker_counts[message.author.display_name] += 1
        channel_dynamics = _build_channel_dynamics(
            speaker_counts,
            message.author.display_name,
            topic_keywords,
        )

        memory_query = clean_content
        if recent_context and len(clean_content) < 40:
            memory_query = f"{clean_content}\n{recent_context}"[-800:]
        memories = await self.memory_manager.retrieve(
            str(message.channel.id), memory_query, limit=self.settings.memory_recall_limit
        )
        # Collect available custom emojis to hint at usage
        emoji_names = []
        try:
            for e in message.guild.emojis if message.guild else []:
                emoji_names.append(str(e))
        except Exception:
            pass
        emoji_block = ", ".join(emoji_names[:30]) if emoji_names else None
        image_descriptions: list[str] = []
        for attachment in message.attachments:
            if attachment.content_type and attachment.content_type.startswith("image/"):
                try:
                    caption = await self.llm_client.describe_image(
                        attachment.url, prompt="Briefly describe this image for conversational context."
                    )
                    image_descriptions.append(caption)
                    logger.info(
                        "Image described for channel=%s attachment=%s caption=%s",
                        message.channel.id,
                        attachment.url,
                        caption,
                    )
                except Exception as exc:
                    logger.warning("Failed to describe image %s: %s", attachment.url, exc)
        name_context = None
        if misnamed:
            name_context = "The user called you 'cel'. Correct them firmly that your name is Sel and you dislike being renamed."
        elif name_called:
            name_context = "You were directly called by name 'Sel'; be attentive to them."
        # Local time awareness
        try:
            tz = zoneinfo.ZoneInfo(self.settings.timezone_name)
            local_time = dt.datetime.now(tz).strftime("%A %Y-%m-%d %H:%M")
        except Exception:
            local_time = None

        # Feature flag: use v2 prompts if enabled for this channel
        build_messages = build_messages_v2 if self.settings.should_use_prompts_v2(str(message.channel.id)) else build_messages_v1

        system_messages = build_messages(
            global_state=global_state,
            channel_state=channel_state,
            memories=memories,
            addressed_user=user_state,
            persona_seed=global_state.base_persona or self.settings.persona_seed,
            recent_context=recent_context,
            name_context=name_context,
            available_emojis=emoji_block,
            image_descriptions=image_descriptions or None,
            local_time=local_time,
            style_hint=style_hint,
            avoid_openers=recent_sel_openers,
            channel_dynamics=channel_dynamics,
        )

        # If message was image-only, enrich user content with image captions so the LLM can react to it
        user_content_for_llm = clean_content
        if not user_content_for_llm and image_descriptions:
            user_content_for_llm = "User shared images:\n" + "\n".join(f"- {d}" for d in image_descriptions)
        elif image_descriptions:
            user_content_for_llm = user_content_for_llm + "\n[Images]\n" + "\n".join(f"- {d}" for d in image_descriptions)

        start = time.perf_counter()
        try:
            response_temp = temperature_for_hormones(hormones, self.settings.openrouter_main_temp)
            reply = await self.llm_client.generate_reply(
                system_messages,
                user_content=user_content_for_llm,
                temperature=response_temp,
            )
        except Exception as exc:
            err_text = f"{type(exc).__name__}: {exc}"
            logger.error("LLM reply generation failed: %s", err_text)
            reply = (
                "My brain call glitched (LLM error). "
                f"It complained: {err_text}. "
                "I'm still reading—try again in a moment."
            )
        reply = _adjust_repeated_opener(reply, recent_sel_openers)
        latency_ms = int((time.perf_counter() - start) * 1000)
        reply_text = (reply or "").strip() or "(no response)"
        # Typing indicator and human-ish delay
        delay = (
            1.5
            - hormones.cortisol
            + hormones.serotonin
            - hormones.melatonin
            - hormones.novelty
            + (0.3 - hormones.dopamine)
            - (0.2 * hormones.curiosity)
            + (0.25 * hormones.patience)
        )
        delay = max(0.2, min(3.5, delay))
        async with message.channel.typing():
            await asyncio.sleep(delay)
            sent_msg = await message.channel.send(reply_text)

        global_state.total_messages_sent += 1
        channel_state.last_response_ts = now
        channel_state.messages_since_response = 0
        async with self.state_manager.session() as session:
            await session.merge(global_state)
            await session.merge(channel_state)
            await session.merge(user_state)
            await session.commit()

        # Track feedback base event
        await self.state_manager.log_feedback(
            sel_message_id=str(sent_msg.id),
            channel_id=str(message.channel.id),
            user_id=str(message.author.id),
            latency_ms=latency_ms,
            sentiment=classification.get("sentiment", "neutral"),
        )
        logger.info(
            "Replied channel=%s latency_ms=%s msg_id=%s",
            message.channel.id,
            latency_ms,
            sent_msg.id,
        )

    async def _dm_approver_suggestions(self, suggestions, context_preview: str) -> None:
        """Send pending suggestions to the configured approver via DM."""

        approver_id = self.settings.approval_user_id
        if not approver_id:
            return
        try:
            user = self.get_user(approver_id) or await self.fetch_user(approver_id)
        except Exception as exc:
            logger.warning("Failed to fetch approver user %s: %s", approver_id, exc)
            return

        lines = [
            "New improvement suggestions need approval:",
        ]
        for s in suggestions[:4]:
            lines.append(f"#{s.id} [{s.category}] {s.summary}")
        lines.append("Context: " + (context_preview or "(none)"))
        lines.append("Reply here with ids to approve/deny (manual step for now).")
        body = "\n".join(lines)

        try:
            await user.send(body)
        except Exception as exc:
            logger.warning("Failed to DM approver %s: %s", approver_id, exc)

    async def _cmd_status(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        global_state = await self.state_manager.ensure_global_state()
        channel_id = str(interaction.channel_id) if interaction.channel_id else "dm"

        # Get hormones from HIM or legacy storage
        if self.hormone_manager:
            cached = await self.hormone_manager.get_state(channel_id)
            hormones = cached.vector
        else:
            channel_state = await self.state_manager.get_channel_state(channel_id)
            hormones = HormoneVector.from_channel(channel_state)

        msg = (
            f"Mood: {hormones.natural_language_summary()}\n"
            f"Teasing: {global_state.teasing_level:.2f} Emoji: {global_state.emoji_rate:.2f} Empathy: {global_state.empathy:.2f}"
        )
        await interaction.followup.send(msg, ephemeral=True)

    async def _cmd_improve(self, interaction: discord.Interaction, context: str) -> None:
        await interaction.response.defer(ephemeral=True)
        suggestions = await self.self_improvement.generate_suggestions(
            context=context,
            proposed_by=interaction.user.name,
        )
        if suggestions:
            lines = [f"#{s.id} [{s.category}] {s.summary}" for s in suggestions]
            await interaction.followup.send("Queued improvements (pending approval):\n" + "\n".join(lines), ephemeral=True)
            await self._dm_approver_suggestions(suggestions, context_preview=context[:160])
        else:
            await interaction.followup.send("No concrete improvements to queue right now.", ephemeral=True)

    async def _cmd_him_status(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        base = self.settings.him_api_base_url
        if not base:
            await interaction.followup.send("HIM API not configured.", ephemeral=True)
            return
        url = base.rstrip("/") + "/v1/snapshots"
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(url, params={"limit": 1})
                msg = f"HIM status {resp.status_code}"
                if resp.status_code == 200:
                    msg += " reachable"
            await interaction.followup.send(msg, ephemeral=True)
        except Exception as exc:
            await interaction.followup.send(f"HIM check failed: {exc}", ephemeral=True)

    async def _cmd_agents(self, interaction: discord.Interaction) -> None:
        if not _is_authorized(interaction.user.id, self.settings.approval_user_id):
            await interaction.response.send_message("Not authorized to manage agents.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        agents = self.agents_manager.list_agents()
        if not agents:
            await interaction.followup.send("No agents found in agents directory.", ephemeral=True)
            return
        lines = [f"{a.name} - {a.description or '(no description)'}" for a in agents]
        await interaction.followup.send("Available agents:\n" + "\n".join(lines), ephemeral=True)

    async def _cmd_run_agent(self, interaction: discord.Interaction, name: str, text: str) -> None:
        if not _is_authorized(interaction.user.id, self.settings.approval_user_id):
            await interaction.response.send_message("Not authorized to run agents.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            result = await self.agents_manager.run_agent_async(name, text)
        except Exception as exc:
            await interaction.followup.send(f"Agent error: {exc}", ephemeral=True)
            return
        await interaction.followup.send(f"{name} → {result}", ephemeral=True)

    async def _cmd_cache_stats(self, interaction: discord.Interaction) -> None:
        """Show LLM response cache statistics."""
        await interaction.response.defer(ephemeral=True)
        if not self.llm_client.cache:
            await interaction.followup.send("Cache is disabled.", ephemeral=True)
            return
        stats = self.llm_client.cache.get_stats()
        msg = (
            f"**Cache Statistics**\n"
            f"Hit rate: {stats['hit_rate']:.1%}\n"
            f"Hits: {stats['hits']:,} | Misses: {stats['misses']:,}\n"
            f"Entries: {stats['entries']:,} | Evictions: {stats['evictions']:,}\n"
            f"Cost saved: ${stats['total_cost_saved_usd']:.4f}"
        )
        await interaction.followup.send(msg, ephemeral=True)

    async def _cmd_agent_stats(self, interaction: discord.Interaction) -> None:
        """Show agent performance statistics."""
        await interaction.response.defer(ephemeral=True)
        agent_stats = self.agents_manager.get_agent_stats()
        if not agent_stats:
            await interaction.followup.send("No agent execution data available.", ephemeral=True)
            return

        lines = ["**Agent Performance Statistics**\n"]
        for agent_name, stats in agent_stats.items():
            if not stats:
                continue
            lines.append(f"**{agent_name}**")
            lines.append(f"  Calls: {stats['total_calls']:,} (cached: {stats['cached_calls']:,})")
            lines.append(f"  Cache hit rate: {stats['cache_hit_rate']:.1%}")
            lines.append(f"  Avg time: {stats['avg_execution_time_ms']:.1f}ms")
            lines.append(f"  Errors: {stats['errors']} ({stats['error_rate']:.1%})")
            lines.append("")

        msg = "\n".join(lines)
        await interaction.followup.send(msg[:2000], ephemeral=True)  # Discord limit

    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        if user.bot or not reaction.message.author or reaction.message.author.id != self.user.id:
            return

        sentiment = "positive" if str(reaction.emoji) in {"👍", "❤️", "😀", "🔥"} else "negative"
        feedback = await self.state_manager.log_feedback(
            sel_message_id=str(reaction.message.id),
            channel_id=str(reaction.message.channel.id),
            user_id=str(user.id),
            latency_ms=0,
            sentiment=sentiment,
        )
        global_state = await self.state_manager.ensure_global_state()
        user_state = await self.state_manager.get_user_state(str(user.id), user.name)
        await apply_feedback(self.state_manager, global_state, user_state, feedback)
        logger.info(
            "Reaction feedback channel=%s message=%s user=%s sentiment=%s",
            reaction.message.channel.id,
            reaction.message.id,
            user.id,
            sentiment,
        )
