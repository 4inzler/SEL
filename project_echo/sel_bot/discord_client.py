"""
Discord client handling message events and orchestrating Sel's logic.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import time
import re
import shutil
import subprocess
import tempfile
import wave
from collections import Counter
from typing import Optional

import discord
from discord import app_commands
try:
    from discord.ext import voice_recv
    VOICE_RECV_AVAILABLE = True
except Exception:
    voice_recv = None
    VOICE_RECV_AVAILABLE = False
import zoneinfo
from sqlalchemy import select
import datetime as dt
import httpx

from .behaviour import (
    extract_greeting_target,
    is_broadcast_greeting_target,
    is_direct_question_to_sel,
)
from .config import Settings
from .feedback import apply_feedback
from .hormones import (
    HormoneVector,
    apply_message_effects,
    decay_channel_hormones,
    apply_silence_drift,
    temperature_for_hormones,
    BASELINE_LEVELS,
)
from .llm_factory import LLMClient
from .memory import MemoryManager
from .hormone_state_manager import HormoneHistoryQuery
from .models import ChannelState, GlobalSelState, UserState
from .prompts import build_messages as build_messages_v1, derive_style_guidance, format_style_hint
from .prompts_v2 import build_messages_v2
from .prompts_v2_simplified import build_messages_v2 as build_messages_v2_simplified
from .self_improvement import SelfImprovementManager
from .state_manager import StateManager
from .presence_tracker import PresenceTracker
from .confidence import ConfidenceScorer
from .gif_analyzer import GifAnalyzer
from .biological_systems import BiologicalState, detect_tone, memory_affects_mood
from .elevenlabs_client import ElevenLabsClient
from .media_utils import (
    normalize_content_type,
    looks_like_image_filename,
    looks_like_image_url,
)
from .vision_analysis import apply_text_override, render_vision_analysis
from . import context as time_weather_context

# Security system imports
try:
    import sys
    from pathlib import Path
    # Add project_echo directory to path
    project_root = Path(__file__).parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from security.async_security_fix import AsyncSELSecurityManager
    from security.html_xss_protection import HTMLXSSDetector
    from security.user_management_system import UserManagementSystem
    SECURITY_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Security system not available: {e}")
    SECURITY_AVAILABLE = False

logger = logging.getLogger(__name__)


async def _keepalive_typing(channel) -> None:
    """Fires trigger_typing() every 8s so the typing indicator stays visible during processing."""
    while True:
        try:
            await channel.trigger_typing()
        except Exception:
            pass
        await asyncio.sleep(8)


def _apply_opus_decode_safety_patch() -> None:
    """Prevent corrupted opus packets from crashing voice receive threads."""
    try:
        from discord import opus as discord_opus
    except Exception as exc:  # pragma: no cover - only runs when discord is installed
        logger.debug("Opus module unavailable for safety patch: %s", exc)
        return
    if getattr(discord_opus, "_sel_safe_decode_patched", False):
        return
    original_decode = getattr(discord_opus.Decoder, "decode", None)
    if original_decode is None:
        return

    def _safe_decode(self, data, fec=False):
        try:
            return original_decode(self, data, fec=fec)
        except discord_opus.OpusError as exc:
            logger.debug("Opus decode error ignored: %s", exc)
            return b""

    discord_opus.Decoder.decode = _safe_decode
    discord_opus._sel_safe_decode_patched = True

if VOICE_RECV_AVAILABLE:
    _apply_opus_decode_safety_patch()


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


_GOAL_COMPLETION_PATTERNS = (
    r"\b(it (works|worked)|that (worked|fixed|did it))\b",
    r"\b(fixed|solved|got it working|got it|all set|done|finished|figured it out|nailed it)\b",
)
_GRATITUDE_MARKERS = (
    "thanks",
    "thank you",
    "thx",
    "ty",
    "appreciate",
    "much appreciated",
    "grateful",
)

_CHANNEL_MENTION_RE = re.compile(r"<#(\d+)>")
_USER_MENTION_RE = re.compile(r"<@!?(\d+)>")


def _merge_effects(*effect_maps: dict[str, float]) -> dict[str, float]:
    combined: dict[str, float] = {}
    for effects in effect_maps:
        for key, delta in effects.items():
            combined[key] = combined.get(key, 0.0) + float(delta)
    return combined


def _apply_effects_to_state(state: ChannelState, effects: dict[str, float]) -> None:
    for hormone, delta in effects.items():
        if hasattr(state, hormone):
            current = getattr(state, hormone) or 0.0
            setattr(state, hormone, _clamp(current + float(delta)))


def _looks_like_goal_completion(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(re.search(pattern, lowered) for pattern in _GOAL_COMPLETION_PATTERNS)


def _looks_like_gratitude(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(marker in lowered for marker in _GRATITUDE_MARKERS)


def _pcm_duration_seconds(byte_count: int, sample_rate: int, channels: int, sample_width: int = 2) -> float:
    bytes_per_second = sample_rate * channels * sample_width
    if bytes_per_second <= 0:
        return 0.0
    return byte_count / bytes_per_second


def _pcm_to_wav_bytes(
    pcm_bytes: bytes,
    *,
    sample_rate: int,
    channels: int,
    sample_width: int = 2,
) -> bytes:
    with io.BytesIO() as buffer:
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(sample_width)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_bytes)
        return buffer.getvalue()


class VoiceMessageProxy:
    def __init__(
        self,
        *,
        author: discord.Member,
        channel: discord.abc.Messageable,
        guild: discord.Guild,
        content: str,
    ) -> None:
        self.author = author
        self.channel = channel
        self.guild = guild
        self.content = content
        self.is_voice_message = True
        self.attachments: list[discord.Attachment] = []
        self.embeds: list[discord.Embed] = []
        self.stickers: list = []
        self.reference = None
        self.mentions: list[discord.Member] = []
        self.id = 0
        self.created_at = dt.datetime.now(tz=dt.timezone.utc)

    async def reply(self, content: str, *, mention_author: bool = False) -> discord.Message:
        allowed_mentions = None
        if not mention_author:
            allowed_mentions = discord.AllowedMentions.none()
        return await self.channel.send(content, allowed_mentions=allowed_mentions)


if VOICE_RECV_AVAILABLE:
    class VoiceTranscriptionSink(voice_recv.AudioSink):
        def __init__(
            self,
            client: "SelDiscordClient",
            *,
            sample_rate: int,
            channels: int,
            min_seconds: float,
            max_seconds: float,
        ) -> None:
            super().__init__()
            self._sel_client = client
            self.sample_rate = sample_rate
            self.channels = channels
            self.min_seconds = min_seconds
            self.max_seconds = max_seconds
            self._buffers: dict[int, bytearray] = {}
            self._sample_width = 2

        def wants_opus(self) -> bool:
            return False

        def cleanup(self) -> None:
            self._buffers.clear()

        def _max_bytes(self) -> int:
            if self.max_seconds <= 0:
                return 0
            return int(self.max_seconds * self.sample_rate * self.channels * self._sample_width)

        def write(self, user, data) -> None:
            if not user or getattr(user, "bot", False):
                return
            pcm = getattr(data, "pcm", None)
            if not pcm:
                return
            buffer = self._buffers.setdefault(user.id, bytearray())
            buffer.extend(pcm)
            max_bytes = self._max_bytes()
            if max_bytes and len(buffer) > max_bytes:
                del buffer[:-max_bytes]

        @voice_recv.AudioSink.listener()
        def on_voice_member_speaking_stop(self, member) -> None:
            if not member or getattr(member, "bot", False):
                return
            pcm = self._buffers.pop(member.id, None)
            if not pcm:
                return
            duration = _pcm_duration_seconds(len(pcm), self.sample_rate, self.channels, self._sample_width)
            if duration < self.min_seconds:
                return
            if self.max_seconds > 0 and duration > self.max_seconds:
                max_bytes = self._max_bytes()
                pcm = pcm[:max_bytes] if max_bytes else pcm
            try:
                asyncio.run_coroutine_threadsafe(
                    self._sel_client._handle_voice_pcm(member, bytes(pcm)),
                    self._sel_client.loop,
                )
            except Exception as exc:
                logger.warning("Failed scheduling voice transcription for %s: %s", member, exc)
def _extract_channel_id(text: str) -> Optional[int]:
    if not text:
        return None
    match = _CHANNEL_MENTION_RE.search(text)
    if match:
        return int(match.group(1))
    candidate = text.strip()
    if candidate.isdigit():
        return int(candidate)
    return None


def _extract_user_id(text: str) -> Optional[int]:
    if not text:
        return None
    match = _USER_MENTION_RE.search(text)
    if match:
        return int(match.group(1))
    candidate = text.strip()
    if candidate.isdigit():
        return int(candidate)
    return None


def _find_voice_channel_by_name(
    guild: discord.Guild,
    channel_name: str,
) -> Optional[discord.abc.GuildChannel]:
    if not channel_name:
        return None
    target = channel_name.strip()
    if target.startswith("#"):
        target = target[1:]
    target = target.lower()
    if not target:
        return None
    candidates = list(guild.voice_channels)
    stage_channels = getattr(guild, "stage_channels", [])
    candidates.extend(stage_channels)
    for channel in candidates:
        if channel.name.lower() == target:
            return channel
    return None


def _memory_mood_effects(memories: list) -> dict[str, float]:
    effects: dict[str, float] = {}
    for mem in (memories or [])[:3]:
        summary = getattr(mem, "summary", "") or ""
        if not summary:
            continue
        mem_effects = memory_affects_mood(summary)
        salience = getattr(mem, "salience", 0.5) or 0.5
        scale = max(0.4, min(1.0, float(salience)))
        for key, delta in mem_effects.items():
            effects[key] = effects.get(key, 0.0) + (float(delta) * scale)
    return effects


def _media_mood_effects(descriptions: list[str]) -> dict[str, float]:
    effects: dict[str, float] = {}
    for desc in (descriptions or [])[:3]:
        mem_effects = memory_affects_mood(desc)
        for key, delta in mem_effects.items():
            effects[key] = effects.get(key, 0.0) + (float(delta) * 0.6)
    return effects


def _baseline_hormone_vector() -> HormoneVector:
    baseline = {k: float(v) for k, v in BASELINE_LEVELS.items()}
    return HormoneVector.from_dict(baseline)


def _sparkline(values: list[float], min_value: float = -1.0, max_value: float = 1.0) -> str:
    if not values:
        return ""
    chars = " .:-=+*#%@"
    span = max(0.001, max_value - min_value)
    line = []
    for value in values:
        clamped = max(min_value, min(max_value, value))
        idx = int(((clamped - min_value) / span) * (len(chars) - 1))
        line.append(chars[idx])
    return "".join(line)


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


def _format_relative_time(timestamp: dt.datetime) -> str:
    """Format a timestamp as a human-readable relative time like '5m ago' or '2h ago'."""
    now = dt.datetime.now(dt.timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=dt.timezone.utc)
    delta = now - timestamp
    seconds = int(delta.total_seconds())

    if seconds < 60:
        return "just now"
    elif seconds < 3600:
        mins = seconds // 60
        return f"{mins}m ago"
    elif seconds < 86400:
        hours = seconds // 3600
        return f"{hours}h ago"
    else:
        days = seconds // 86400
        return f"{days}d ago"


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


def _attachment_looks_like_image(attachment: discord.Attachment) -> bool:
    content_type = normalize_content_type(attachment.content_type)
    if content_type:
        if content_type.startswith("image/"):
            return True
        if content_type == "application/octet-stream":
            return looks_like_image_filename(attachment.filename) or looks_like_image_url(attachment.url)
        return False
    if looks_like_image_filename(attachment.filename):
        return True
    return looks_like_image_url(attachment.url)


_AUDIO_EXTENSIONS = {
    ".mp3",
    ".wav",
    ".ogg",
    ".m4a",
    ".aac",
    ".flac",
    ".webm",
    ".mp4",
    ".mov",
}


def _looks_like_audio_filename(name: Optional[str]) -> bool:
    if not name:
        return False
    lowered = name.lower()
    return any(lowered.endswith(ext) for ext in _AUDIO_EXTENSIONS)


def _attachment_looks_like_audio(attachment: discord.Attachment) -> bool:
    content_type = normalize_content_type(attachment.content_type)
    if content_type:
        if content_type.startswith("audio/"):
            return True
        if content_type in {"video/ogg", "video/webm", "video/mp4"}:
            return True
        if content_type == "application/octet-stream":
            return _looks_like_audio_filename(attachment.filename) or _looks_like_audio_filename(attachment.url)
        return False
    return _looks_like_audio_filename(attachment.filename) or _looks_like_audio_filename(attachment.url)


def _tts_output_suffix(output_format: str) -> str:
    lowered = (output_format or "").lower()
    if "wav" in lowered or "pcm" in lowered:
        return ".wav"
    if "ogg" in lowered:
        return ".ogg"
    return ".mp3"


def _clean_text_for_tts(text: str, max_chars: int) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"```.*?```", "", text, flags=re.S)
    cleaned = re.sub(r"`([^`]*)`", r"\1", cleaned)
    cleaned = re.sub(r"https?://\S+", "", cleaned)
    cleaned = re.sub(r"<@!?\\d+>", "", cleaned)
    cleaned = cleaned.replace("\n", " ").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if max_chars > 0 and len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars].rstrip()
        cleaned = cleaned.rstrip(".,;:! ") + "..."
    return cleaned.strip()


def _local_tts_available() -> bool:
    return shutil.which("espeak-ng") is not None


def _piper_tts_available() -> bool:
    return shutil.which("piper") is not None


def _extract_embed_image_urls(embed: discord.Embed) -> list[str]:
    urls: list[str] = []
    image = getattr(embed, "image", None)
    if image and image.url:
        urls.append(image.url)
    thumbnail = getattr(embed, "thumbnail", None)
    if thumbnail and thumbnail.url:
        urls.append(thumbnail.url)
    video = getattr(embed, "video", None)
    if video and video.url:
        urls.append(video.url)
    if embed.url:
        urls.append(embed.url)
    return urls


def _sticker_content_type(sticker: discord.StickerItem) -> Optional[str]:
    try:
        if sticker.format == discord.StickerFormatType.gif:
            return "image/gif"
        if sticker.format in (discord.StickerFormatType.png, discord.StickerFormatType.apng):
            return "image/png"
    except Exception:
        return None
    return None


def _add_human_touches(reply: str, hormones: HormoneVector) -> str:
    """
    DISABLED: Fake typo injection removed for security audit compliance.

    Previously injected manufactured typos (missing apostrophes, etc.).
    This was identified in security audit as potentially undermining trust
    and making the bot appear malfunctioning.

    Authenticity should come from the language model and prompt engineering,
    not from manufactured errors injected post-generation.

    Function kept for backwards compatibility but now returns input unchanged.
    """
    # Return reply unchanged - no manufactured typos
    return reply


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


def _is_authorized(user_id: int, allowed_id: Optional[int]) -> bool:
    return allowed_id is None or user_id == allowed_id


class SelDiscordClient(discord.Client):
    def __init__(
        self,
        settings: Settings,
        state_manager: StateManager,
        llm_client: LLMClient,
        memory_manager: MemoryManager,
        hormone_manager=None,  # Optional HormoneStateManager
        **kwargs,
    ):
        intents = kwargs.pop("intents", discord.Intents.default())
        intents.message_content = True
        intents.messages = True
        intents.reactions = True
        intents.presences = True  # Enable presence tracking
        intents.members = True    # Required for presence
        intents.voice_states = True  # Required for voice channel tracking
        super().__init__(intents=intents, **kwargs)

        self.settings = settings
        self.state_manager = state_manager
        self.llm_client = llm_client
        self.memory_manager = memory_manager
        self.hormone_manager = hormone_manager  # HIM-based hormone storage (optional)
        self.self_improvement = SelfImprovementManager(state_manager, llm_client)
        from .seal_self_edit import SEALSelfEditor
        self.seal_editor = SEALSelfEditor(
            llm_client=llm_client,
            memory_manager=memory_manager,
            self_improvement=self.self_improvement,
            state_manager=state_manager,
            settings=settings,
            agents_dir=settings.agents_dir,
            data_dir=getattr(settings, "sel_data_dir", "./sel_data"),
        )
        self.seal_task: Optional[asyncio.Task] = None
        self.presence_tracker = PresenceTracker()  # Track Discord presence
        self.confidence_scorer = ConfidenceScorer()  # Track response confidence
        self.decay_task: Optional[asyncio.Task] = None
        self.ping_task: Optional[asyncio.Task] = None
        self.daily_summary_task: Optional[asyncio.Task] = None
        self.checkin_task: Optional[asyncio.Task] = None
        self.voice_auto_leave_task: Optional[asyncio.Task] = None
        self._tts_task: Optional[asyncio.Task] = None
        self._tts_queue: Optional[asyncio.Queue] = None
        self.elevenlabs_client: Optional[ElevenLabsClient] = None
        self.tree = app_commands.CommandTree(self)
        self.following_user_id: Optional[int] = None  # Track which user SEL is following in voice
        self.biological_state = BiologicalState()
        self._bio_lock = asyncio.Lock()
        self._bio_loaded = False
        self._bio_dirty = False
        self._daily_summary_sent: dict[int, str] = {}
        self._checkin_last_sent: dict[int, dt.datetime] = {}
        self.voice_empty_since: dict[int, dt.datetime] = {}
        self.voice_announce_channel_ids: dict[int, int] = {}
        self.voice_sinks: dict[int, object] = {}
        self.voice_listen_restart_at: dict[int, float] = {}

        # Message batching: collect multiple messages that arrive quickly
        self.pending_messages: dict[int, list[discord.Message]] = {}  # channel_id -> list of messages
        self.batch_timers: dict[int, asyncio.Task] = {}  # channel_id -> timer task
        self.batch_window_seconds = 2.5  # Wait this long to collect messages before responding

        # Spam protection: track message timestamps per user per channel
        self.user_message_timestamps: dict[tuple[int, int], list[float]] = {}  # (channel_id, user_id) -> [timestamps]

        # GIF analyzer for understanding animated GIFs
        self.gif_analyzer = GifAnalyzer(max_frames=5, frame_skip=3)

        # Global mood/memory IDs (single unified state like a real person)
        self._global_mood_id = settings.global_mood_id if settings.global_mood_enabled else None
        self._global_memory_id = settings.global_memory_id if settings.global_memory_enabled else None

        if settings.elevenlabs_api_key and (settings.elevenlabs_tts_enabled or settings.elevenlabs_stt_enabled):
            self.elevenlabs_client = ElevenLabsClient(
                settings.elevenlabs_api_key,
                base_url=settings.elevenlabs_base_url,
            )
            if settings.elevenlabs_tts_enabled:
                self._tts_queue = asyncio.Queue()
        elif settings.elevenlabs_tts_enabled or settings.elevenlabs_stt_enabled:
            logger.warning("ElevenLabs enabled but ELEVENLABS_API_KEY is missing; disabling TTS/STT.")
        if (settings.piper_tts_enabled or settings.local_tts_enabled) and self._tts_queue is None:
            self._tts_queue = asyncio.Queue()

        # Security system initialization
        if SECURITY_AVAILABLE:
            logger.info("Initializing security system...")
            try:
                self.async_security = AsyncSELSecurityManager(
                    api_client=llm_client,
                    enable_privacy=True,
                    enable_advanced_detection=True,
                    log_all_checks=True,
                    max_processing_time=5.0,  # Prevent heartbeat blocking
                )
                self.user_manager = UserManagementSystem()
                # Set owner (rinexis_)
                self.user_manager._initialize_owner()
                logger.info("Security system initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize security system: {e}")
                self.async_security = None
                self.user_manager = None
        else:
            self.async_security = None
            self.user_manager = None
            logger.warning("Running WITHOUT security system - vulnerable to attacks!")

    def _get_mood_id(self, channel_id: str) -> str:
        """Get the mood state ID - global if enabled, otherwise per-channel."""
        return self._global_mood_id or channel_id

    def _get_memory_id(self, channel_id: str) -> str:
        """Get the memory storage ID - global if enabled, otherwise per-channel."""
        return self._global_memory_id or channel_id

    def _select_prompt_builder(self, channel_id: str):
        """
        Choose prompt builder and variant label based on rollout settings.
        """
        variant = self.settings.select_prompt_variant(channel_id)
        if variant == "v2_simplified":
            return build_messages_v2_simplified, variant
        if variant == "v2_full":
            return build_messages_v2, variant
        return build_messages_v1, "v1"

    def _is_admin(self, user_id: int) -> bool:
        return _is_authorized(user_id, self.settings.approval_user_id)

    async def _send_daily_summary(self, channel_id: int) -> None:
        if not self.settings.is_channel_allowed(channel_id):
            return
        global_state = await self.state_manager.ensure_global_state()
        if global_state.responses_paused:
            return
        channel = self.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.fetch_channel(channel_id)
            except Exception as exc:
                logger.warning("Unable to fetch channel %s for daily summary: %s", channel_id, exc)
                return

        mood_id = self._get_mood_id(str(channel_id))
        if self.hormone_manager:
            cached = await self.hormone_manager.get_state(mood_id)
            hormones = cached.vector
        else:
            channel_state = await self.state_manager.get_channel_state(str(channel_id))
            hormones = HormoneVector.from_channel(channel_state)

        memory_id = self._get_memory_id(str(channel_id))
        memories = await self.memory_manager.retrieve_recent(memory_id, limit=6)
        topics = _extract_topic_keywords([m.summary for m in memories if m.summary])
        topic_line = f"Topics: {', '.join(topics)}." if topics else "Topics: none."

        mood_line = f"Today feels {hormones.natural_language_summary()}."
        summary = f"Daily check-in: {mood_line} {topic_line} How's everyone doing?"

        try:
            await channel.send(summary)
        except Exception as exc:
            logger.warning("Failed to send daily summary to channel %s: %s", channel_id, exc)

    async def _daily_summary_loop(self) -> None:
        if not self.settings.daily_summary_enabled:
            return
        channel_ids = self.settings.daily_summary_channel_ids or []
        if not channel_ids:
            return
        while True:
            try:
                tz = zoneinfo.ZoneInfo(self.settings.timezone_name)
            except Exception:
                tz = dt.timezone.utc
            now = dt.datetime.now(tz)
            target = now.replace(
                hour=self.settings.daily_summary_hour,
                minute=self.settings.daily_summary_minute,
                second=0,
                microsecond=0,
            )
            if target <= now:
                target = target + dt.timedelta(days=1)
            sleep_for = (target - now).total_seconds()
            await asyncio.sleep(max(60, sleep_for))
            today = target.date().isoformat()
            for channel_id in channel_ids:
                if self._daily_summary_sent.get(channel_id) == today:
                    continue
                await self._send_daily_summary(channel_id)
                self._daily_summary_sent[channel_id] = today

    async def _scheduled_checkin_loop(self) -> None:
        if not self.settings.scheduled_checkin_enabled:
            return
        channel_ids = self.settings.scheduled_checkin_channel_ids or []
        if not channel_ids:
            return
        while True:
            global_state = await self.state_manager.ensure_global_state()
            if global_state.responses_paused:
                await asyncio.sleep(300)
                continue
            try:
                tz = zoneinfo.ZoneInfo(self.settings.timezone_name)
            except Exception:
                tz = dt.timezone.utc
            now = dt.datetime.now(tz)
            target = now.replace(
                hour=self.settings.scheduled_checkin_hour,
                minute=self.settings.scheduled_checkin_minute,
                second=0,
                microsecond=0,
            )
            if target <= now:
                target = target + dt.timedelta(days=1)
            sleep_for = (target - now).total_seconds()
            await asyncio.sleep(max(60, sleep_for))
            for channel_id in channel_ids:
                if not self.settings.is_channel_allowed(channel_id):
                    continue
                channel = self.get_channel(channel_id)
                if channel is None:
                    try:
                        channel = await self.fetch_channel(channel_id)
                    except Exception as exc:
                        logger.warning("Unable to fetch channel %s for scheduled check-in: %s", channel_id, exc)
                        continue
                try:
                    last_message = None
                    async for msg in channel.history(limit=1, oldest_first=False):
                        last_message = msg
                        break
                except Exception:
                    last_message = None
                if last_message:
                    delta_hours = (dt.datetime.now(tz=dt.timezone.utc) - last_message.created_at).total_seconds() / 3600
                    if delta_hours < self.settings.scheduled_checkin_min_inactive_hours:
                        continue
                last_sent = self._checkin_last_sent.get(channel_id)
                if last_sent and (dt.datetime.now(tz=dt.timezone.utc) - last_sent).total_seconds() < 3600:
                    continue
                try:
                    await channel.send("hey, quick check-in — how's everyone doing today?")
                    self._checkin_last_sent[channel_id] = dt.datetime.now(tz=dt.timezone.utc)
                except Exception as exc:
                    logger.warning("Failed to send scheduled check-in to channel %s: %s", channel_id, exc)

    async def _ensure_biological_state_loaded(
        self,
        global_state: Optional[GlobalSelState] = None,
    ) -> GlobalSelState:
        if global_state is None:
            global_state = await self.state_manager.ensure_global_state()
        if self._bio_loaded:
            return global_state
        async with self._bio_lock:
            if not self._bio_loaded:
                payload = getattr(global_state, "biological_state", None) or {}
                self.biological_state = (
                    BiologicalState.from_dict(payload) if payload else BiologicalState()
                )
                self._bio_loaded = True
        return global_state

    async def _transcribe_audio_attachments(
        self,
        attachments: list[discord.Attachment],
    ) -> list[str]:
        if not attachments:
            return []
        if not (self.settings.elevenlabs_stt_enabled and self.elevenlabs_client):
            return []

        transcripts: list[str] = []
        max_bytes = max(0, int(self.settings.elevenlabs_stt_max_bytes))
        for attachment in attachments:
            if not _attachment_looks_like_audio(attachment):
                continue
            if max_bytes and attachment.size and attachment.size > max_bytes:
                logger.info(
                    "Skipping audio attachment over max size: %s bytes for %s",
                    attachment.size,
                    attachment.filename,
                )
                continue
            try:
                audio_bytes = await attachment.read()
                if max_bytes and len(audio_bytes) > max_bytes:
                    logger.info(
                        "Skipping audio attachment over max size after read: %s bytes for %s",
                        len(audio_bytes),
                        attachment.filename,
                    )
                    continue
                result = await self.elevenlabs_client.transcribe(
                    audio_bytes=audio_bytes,
                    filename=attachment.filename or "audio",
                    model_id=self.settings.elevenlabs_stt_model,
                    language_code=self.settings.elevenlabs_stt_language_code or None,
                    content_type=normalize_content_type(attachment.content_type) or None,
                    enable_logging=self.settings.elevenlabs_stt_enable_logging,
                )
                text = (
                    (result.get("text") if isinstance(result, dict) else None)
                    or (result.get("transcript") if isinstance(result, dict) else None)
                    or (result.get("transcription") if isinstance(result, dict) else None)
                )
                if text:
                    transcripts.append(str(text).strip())
                if len(transcripts) >= 2:
                    break
            except Exception as exc:
                logger.warning("Audio transcription failed for %s: %s", attachment.filename, exc)
        return [t for t in transcripts if t]

    async def _maybe_queue_tts(self, message: discord.Message, reply_text: str) -> None:
        tts_available = bool(self._tts_queue) and (
            (self.settings.elevenlabs_tts_enabled and self.elevenlabs_client)
            or self.settings.piper_tts_enabled
            or self.settings.local_tts_enabled
        )
        if not tts_available:
            return
        if not message.guild:
            return
        voice_client = message.guild.voice_client
        if voice_client is None or not voice_client.is_connected():
            return
        if (
            self.settings.elevenlabs_tts_enabled
            and self.elevenlabs_client
            and not self.settings.elevenlabs_voice_id
            and not self.settings.local_tts_enabled
            and not self.settings.piper_tts_enabled
        ):
            logger.warning("TTS enabled but ELEVENLABS_VOICE_ID is missing; skipping playback.")
            return
        cleaned = _clean_text_for_tts(reply_text, self.settings.elevenlabs_tts_max_chars)
        if not cleaned:
            return
        await self._tts_queue.put((message.guild.id, message.channel.id, cleaned))

    async def _synthesize_local_tts(self, text: str) -> Optional[bytes]:
        if not self.settings.local_tts_enabled:
            return None
        if not _local_tts_available():
            logger.warning("LOCAL_TTS_ENABLED is true but espeak-ng is not installed.")
            return None
        voice = (self.settings.local_tts_voice or "").strip()

        def _render() -> Optional[bytes]:
            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                    tmp_path = tmp.name
                cmd = ["espeak-ng", "-w", tmp_path]
                if voice:
                    cmd += ["-v", voice]
                cmd.append(text)
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                with open(tmp_path, "rb") as handle:
                    return handle.read()
            except Exception as exc:
                logger.warning("Local TTS failed: %s", exc)
                return None
            finally:
                if tmp_path:
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass

        return await asyncio.to_thread(_render)

    async def _synthesize_piper_tts(self, text: str) -> Optional[bytes]:
        if not self.settings.piper_tts_enabled:
            return None
        if not _piper_tts_available():
            logger.warning("PIPER_TTS_ENABLED is true but piper is not installed.")
            return None
        model = (self.settings.piper_tts_model or "").strip()
        if not model:
            logger.warning("PIPER_TTS_ENABLED is true but PIPER_TTS_MODEL is empty.")
            return None
        data_dir = (self.settings.piper_tts_data_dir or "").strip()
        download_dir = (self.settings.piper_tts_download_dir or "").strip()

        def _render() -> Optional[bytes]:
            tmp_path = None
            try:
                if data_dir:
                    os.makedirs(data_dir, exist_ok=True)
                if download_dir:
                    os.makedirs(download_dir, exist_ok=True)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                    tmp_path = tmp.name
                cmd = ["piper", "--model", model, "--output_file", tmp_path]
                if data_dir:
                    cmd += ["--data-dir", data_dir]
                if download_dir:
                    cmd += ["--download-dir", download_dir]
                subprocess.run(
                    cmd,
                    input=text.encode("utf-8"),
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                with open(tmp_path, "rb") as handle:
                    return handle.read()
            except Exception as exc:
                logger.warning("Piper TTS failed: %s", exc)
                return None
            finally:
                if tmp_path:
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass

        return await asyncio.to_thread(_render)

    async def _tts_loop(self) -> None:
        if not self._tts_queue:
            return
        while True:
            try:
                guild_id, channel_id, text = await self._tts_queue.get()
                guild = self.get_guild(guild_id)
                if not guild or not guild.voice_client:
                    continue
                voice_client = guild.voice_client
                if voice_client is None or not voice_client.is_connected():
                    continue
                if voice_client.is_playing() or voice_client.is_paused():
                    while voice_client.is_playing() or voice_client.is_paused():
                        await asyncio.sleep(0.1)

                audio_bytes = None
                suffix = None
                if self.settings.piper_tts_enabled:
                    audio_bytes = await self._synthesize_piper_tts(text)
                    if audio_bytes:
                        suffix = ".wav"
                if audio_bytes is None and self.settings.elevenlabs_tts_enabled and self.elevenlabs_client:
                    try:
                        audio_bytes = await self.elevenlabs_client.synthesize(
                            text=text,
                            voice_id=self.settings.elevenlabs_voice_id,
                            model_id=self.settings.elevenlabs_tts_model,
                            output_format=self.settings.elevenlabs_tts_output_format,
                            language_code=self.settings.elevenlabs_tts_language_code or None,
                            enable_logging=self.settings.elevenlabs_tts_enable_logging,
                        )
                        suffix = _tts_output_suffix(self.settings.elevenlabs_tts_output_format)
                    except Exception as exc:
                        logger.warning("ElevenLabs TTS failed: %s", exc)
                if audio_bytes is None and self.settings.local_tts_enabled:
                    audio_bytes = await self._synthesize_local_tts(text)
                    if audio_bytes:
                        suffix = ".wav"
                if not audio_bytes or not suffix:
                    continue
                temp_path = None
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                        tmp.write(audio_bytes)
                        temp_path = tmp.name
                    done = asyncio.Event()

                    def _after_playback(error):
                        if error:
                            logger.warning("TTS playback error in guild %s: %s", guild_id, error)
                        try:
                            self.loop.call_soon_threadsafe(done.set)
                        except Exception:
                            pass

                    source = discord.FFmpegPCMAudio(temp_path)
                    try:
                        voice_client.play(source, after=_after_playback)
                    except Exception as exc:
                        logger.warning("Failed to start TTS playback: %s", exc)
                        done.set()
                    await done.wait()
                finally:
                    if temp_path:
                        try:
                            os.remove(temp_path)
                        except OSError:
                            pass
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("TTS loop error: %s", exc)
            finally:
                try:
                    self._tts_queue.task_done()
                except Exception:
                    pass

    async def setup_hook(self) -> None:
        self.decay_task = asyncio.create_task(self._decay_loop())
        self.ping_task = asyncio.create_task(self._inactive_ping_loop())
        if self.settings.seal_enabled:
            self.seal_task = asyncio.create_task(self.seal_editor.run_loop())
        self.daily_summary_task = asyncio.create_task(self._daily_summary_loop())
        self.checkin_task = asyncio.create_task(self._scheduled_checkin_loop())
        if self.settings.voice_auto_leave_enabled:
            self.voice_auto_leave_task = asyncio.create_task(self._voice_auto_leave_loop())
        if self._tts_queue and (
            self.settings.elevenlabs_tts_enabled
            or self.settings.piper_tts_enabled
            or self.settings.local_tts_enabled
        ):
            self._tts_task = asyncio.create_task(self._tts_loop())
        self.tree.add_command(app_commands.Command(name="sel_status", description="Show Sel's mood and channel state", callback=self._cmd_status))
        self.tree.add_command(app_commands.Command(name="sel_improve", description="Queue self-improvement suggestions", callback=self._cmd_improve))
        self.tree.add_command(app_commands.Command(name="him_status", description="Check HIM API connectivity", callback=self._cmd_him_status))
        self.tree.add_command(app_commands.Command(name="sel_cache_stats", description="Show LLM response cache statistics", callback=self._cmd_cache_stats))
        self.tree.add_command(app_commands.Command(name="sel_confidence", description="Show response confidence statistics", callback=self._cmd_confidence))
        self.tree.add_command(app_commands.Command(name="sel_bulk_delete", description="Bulk delete messages from a specific user (admin only)", callback=self._cmd_bulk_delete))
        self.tree.add_command(app_commands.Command(name="sel_purge_user", description="Remove all memories/data for a user (admin only)", callback=self._cmd_purge_user_data))
        self.tree.add_command(app_commands.Command(name="sel_reset_mood", description="Reset Sel's mood hormones (admin only)", callback=self._cmd_reset_mood))
        self.tree.add_command(app_commands.Command(name="sel_set_cycle_day", description="Set menstrual cycle day (admin only)", callback=self._cmd_set_cycle_day))
        self.tree.add_command(app_commands.Command(name="sel_set_attachment", description="Set attachment style (admin only)", callback=self._cmd_set_attachment))
        self.tree.add_command(app_commands.Command(name="sel_debug_bio", description="Show biological system debug info (admin only)", callback=self._cmd_debug_bio))
        self.tree.add_command(app_commands.Command(name="sel_pause", description="Pause Sel replies (admin only)", callback=self._cmd_pause))
        self.tree.add_command(app_commands.Command(name="sel_resume", description="Resume Sel replies (admin only)", callback=self._cmd_resume))
        self.tree.add_command(app_commands.Command(name="sel_mood_timeline", description="Show mood timeline for a hormone", callback=self._cmd_mood_timeline))
        try:
            await self.tree.sync()
        except Exception as exc:
            logger.warning("Failed to sync slash commands: %s", exc)

    async def close(self) -> None:
        if self.decay_task:
            self.decay_task.cancel()
        if self.ping_task:
            self.ping_task.cancel()
        if self.seal_task:
            self.seal_task.cancel()
        if self.daily_summary_task:
            self.daily_summary_task.cancel()
        if self.checkin_task:
            self.checkin_task.cancel()
        if self.voice_auto_leave_task:
            self.voice_auto_leave_task.cancel()
        if self._tts_task:
            self._tts_task.cancel()
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

                await self._ensure_biological_state_loaded()
                local_ref = local_now or dt.datetime.now(tz=dt.timezone.utc)
                local_hour = local_ref.hour
                local_date = local_ref.date().isoformat()
                is_sleep_hours = local_hour >= 23 or local_hour < 7
                now_utc = dt.datetime.now(tz=dt.timezone.utc)

                active_recently = False
                hours_inactive: Optional[float] = None
                last_activity_channel_id: Optional[str] = None
                bio_effects: dict[str, float] = {}
                daily_stress_effects: dict[str, float] = {}
                dream_effects: dict[str, float] = {}

                async with self._bio_lock:
                    last_activity_ts = self.biological_state.last_activity_ts
                    if last_activity_ts and last_activity_ts.tzinfo is None:
                        last_activity_ts = last_activity_ts.replace(tzinfo=dt.timezone.utc)
                        self.biological_state.last_activity_ts = last_activity_ts
                    if last_activity_ts:
                        hours_inactive = (now_utc - last_activity_ts).total_seconds() / 3600
                        active_recently = hours_inactive < 0.25
                    minutes_active = 1.0 if active_recently else 0.0
                    last_activity_channel_id = self.biological_state.last_activity_channel_id
                    bio_effects = self.biological_state.get_all_effects(
                        local_hour,
                        latitude=self.settings.weather_latitude,
                        minutes_active=minutes_active,
                    )
                    if is_sleep_hours and not active_recently:
                        self.biological_state.sleep_inactive_minutes += 1
                    else:
                        if self.biological_state.sleep_inactive_minutes:
                            self.biological_state.sleep_debt.recover_sleep(
                                self.biological_state.sleep_inactive_minutes / 60.0
                            )
                            self.biological_state.sleep_inactive_minutes = 0
                    if not self.biological_state.last_daily_rollover:
                        self.biological_state.last_daily_rollover = local_date
                    elif self.biological_state.last_daily_rollover != local_date:
                        if self.biological_state.daily_cortisol_samples > 0:
                            avg_cortisol = (
                                self.biological_state.daily_cortisol_sum
                                / self.biological_state.daily_cortisol_samples
                            )
                            daily_stress_effects = self.biological_state.stress.daily_accumulation(avg_cortisol)
                        self.biological_state.daily_cortisol_sum = 0.0
                        self.biological_state.daily_cortisol_samples = 0
                        self.biological_state.last_daily_rollover = local_date
                    self._bio_dirty = True

                if hours_inactive and hours_inactive >= 4 and is_sleep_hours:
                    memory_id = self._global_memory_id or last_activity_channel_id
                    recent_memories = []
                    if memory_id:
                        try:
                            recent_memories = await self.memory_manager.retrieve_recent(memory_id, limit=10)
                        except Exception as exc:
                            logger.warning("Failed to fetch memories for dream processing: %s", exc)
                    dream_payload = [{"summary": mem.summary} for mem in recent_memories]
                    async with self._bio_lock:
                        dream_effects, dream_summary = self.biological_state.dreams.process_dreams(
                            hours_inactive,
                            dream_payload,
                        )
                        if dream_effects:
                            self._bio_dirty = True
                    if dream_effects:
                        logger.info("Dream processing applied effects=%s summary=%s", dream_effects, dream_summary)

                combined_bio_effects = _merge_effects(bio_effects, daily_stress_effects, dream_effects)
                avg_cortisol_sum = 0.0
                avg_cortisol_count = 0

                if self.hormone_manager:
                    # HIM-based hormone decay (in-memory cache)
                    # With global mood, we only have one state to decay
                    now = dt.datetime.now(tz=dt.timezone.utc)

                    # Get weather effects (applies globally)
                    weather_effects = time_weather_context.get_weather_hormone_effects()
                    time_effects = time_weather_context.get_time_hormone_effects()

                    async with self.hormone_manager._cache_lock:
                        for mood_id, cached_state in self.hormone_manager._cache.items():
                            # Apply decay to hormone vector (includes circadian rhythms)
                            cached_state.vector.decay(local_time=local_now)

                            # Apply weather effects (rain makes sleepy, sun boosts mood, etc.)
                            if weather_effects:
                                from .hormones import _clamp as h_clamp
                                for hormone, delta in weather_effects.items():
                                    if hasattr(cached_state.vector, hormone):
                                        current = getattr(cached_state.vector, hormone)
                                        # Apply weather effect scaled down (it's per-minute in decay loop)
                                        setattr(cached_state.vector, hormone, h_clamp(current + delta * 0.1))

                            # Apply time-of-day effects (late night loneliness, morning alertness)
                            if time_effects:
                                from .hormones import _clamp as h_clamp
                                for hormone, delta in time_effects.items():
                                    if hasattr(cached_state.vector, hormone):
                                        current = getattr(cached_state.vector, hormone)
                                        setattr(cached_state.vector, hormone, h_clamp(current + delta * 0.1))

                            if combined_bio_effects:
                                cached_state.vector.apply(combined_bio_effects)

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

                            avg_cortisol_sum += cached_state.vector.cortisol
                            avg_cortisol_count += 1
                            cached_state.dirty = True  # Mark for persistence
                            cached_state.last_updated = now

                    if avg_cortisol_count > 0:
                        async with self._bio_lock:
                            self.biological_state.daily_cortisol_sum += avg_cortisol_sum / avg_cortisol_count
                            self.biological_state.daily_cortisol_samples += 1
                            self._bio_dirty = True

                    # Global personality drift (still uses state_manager)
                    async with self.state_manager.session() as session:
                        g_state = (await session.execute(select(GlobalSelState))).scalar_one_or_none()
                        if g_state:
                            if self.hormone_manager._cache:
                                # Average dopamine across all cached channels
                                dopamine_avg = sum(
                                    s.vector.dopamine for s in self.hormone_manager._cache.values()
                                ) / max(1, len(self.hormone_manager._cache))

                                drift = max(0.0, min(0.01, dopamine_avg))
                                g_state.playfulness = min(1.0, g_state.playfulness + drift)
                                g_state.empathy = max(0.0, min(1.0, g_state.empathy + (-drift / 2)))

                            if self._bio_dirty:
                                async with self._bio_lock:
                                    if self._bio_dirty:
                                        g_state.biological_state = self.biological_state.to_dict()
                                        self._bio_dirty = False
                            await session.merge(g_state)
                            await session.commit()

                else:
                    # Legacy SQLAlchemy hormone storage
                    weather_effects = time_weather_context.get_weather_hormone_effects()
                    time_effects = time_weather_context.get_time_hormone_effects()

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

                            # Apply weather effects
                            if weather_effects:
                                for hormone, delta in weather_effects.items():
                                    if hasattr(state, hormone):
                                        current = getattr(state, hormone) or 0.0
                                        setattr(state, hormone, _clamp(current + delta * 0.1))

                            # Apply time effects
                            if time_effects:
                                for hormone, delta in time_effects.items():
                                    if hasattr(state, hormone):
                                        current = getattr(state, hormone) or 0.0
                                        setattr(state, hormone, _clamp(current + delta * 0.1))

                            if combined_bio_effects:
                                _apply_effects_to_state(state, combined_bio_effects)

                            avg_cortisol_sum += state.cortisol or 0.0
                            avg_cortisol_count += 1
                            await session.merge(state)
                        if avg_cortisol_count > 0:
                            async with self._bio_lock:
                                self.biological_state.daily_cortisol_sum += avg_cortisol_sum / avg_cortisol_count
                                self.biological_state.daily_cortisol_samples += 1
                                self._bio_dirty = True
                        g_state = (await session.execute(select(GlobalSelState))).scalar_one_or_none()
                        if g_state:
                            # personality drift slightly toward calmer if low cortisol, more playful with novelty
                            drift = max(0.0, min(0.01, sum(s.dopamine for s in channels) / (len(channels) + 1)))
                            g_state.playfulness = min(1.0, g_state.playfulness + drift)
                            g_state.empathy = max(0.0, min(1.0, g_state.empathy + (-drift / 2)))
                            if self._bio_dirty:
                                async with self._bio_lock:
                                    if self._bio_dirty:
                                        g_state.biological_state = self.biological_state.to_dict()
                                        self._bio_dirty = False
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
        global_state = await self.state_manager.ensure_global_state()
        if global_state.responses_paused:
            return
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
        # Global memory - remember user across all channels
        memory_id = self._get_memory_id(str(channel.id))
        memories = await self.memory_manager.retrieve(memory_id, user_state.handle, limit=max(3, self.settings.memory_recall_limit // 2))

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

        # Feature flag: use configured prompt variant for this channel
        build_messages, prompt_variant = self._select_prompt_builder(str(channel.id))
        logger.info(
            "Prompt variant %s selected for inactivity ping channel=%s user=%s",
            prompt_variant,
            channel.id,
            user_state.user_id,
        )

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

        # Initialize presence tracking for all guilds
        for guild in self.guilds:
            for member in guild.members:
                if not member.bot and member.status != discord.Status.offline:
                    self.presence_tracker.update_presence(member)
            logger.info(f"Initialized presence tracking for {guild.name} ({len([m for m in guild.members if not m.bot])} members)")

    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        """Track presence changes (status, activities)"""
        if after.bot:
            return

        # Update presence cache
        self.presence_tracker.update_presence(after)

        # Log significant changes
        if before.status != after.status:
            logger.debug(f"Presence change: {after.display_name} is now {after.status}")

    async def _process_batched_messages(self, channel_id: int):
        """
        Process all pending messages for a channel after the batch window expires.
        Responds to all messages at once instead of individually.
        """
        # Get and clear pending messages
        messages = self.pending_messages.pop(channel_id, [])
        self.batch_timers.pop(channel_id, None)

        if not messages:
            return

        logger.info(
            "Processing batch of %d messages for channel %s",
            len(messages),
            channel_id
        )

        # Process the batch by handling the most recent message, but include context from all
        # The most recent message determines whether SEL responds
        latest_message = messages[-1]

        combined_content: Optional[str] = None
        force_addressed = False
        try:
            bot_name = self.user.name if self.user else "sel"
            batch_items: list[tuple[discord.Message, str]] = []
            authors_seen: set[int] = set()
            for msg in messages:
                if msg.author.bot:
                    continue
                content = (msg.content or "").strip()
                if not content:
                    continue
                lowered = content.lower()
                addressed = False
                if self.user and self.user in msg.mentions:
                    addressed = True
                if _name_called(lowered, bot_name) or is_direct_question_to_sel(content, bot_name):
                    addressed = True
                if msg.reference and msg.reference.resolved and self.user:
                    resolved = msg.reference.resolved
                    if resolved.author and resolved.author.id == self.user.id:
                        addressed = True
                if addressed:
                    batch_items.append((msg, content))
                    authors_seen.add(msg.author.id)
            if batch_items:
                if len(authors_seen) >= 2:
                    lines = []
                    for msg, content in batch_items[:4]:
                        lines.append(f"- {msg.author.display_name}: {content}")
                    combined_content = (
                        "Multiple people asked at once. Reply in ONE message and address each person by name. "
                        "Do not split into multiple messages.\n"
                        "Questions:\n" + "\n".join(lines)
                    )
                    force_addressed = True
                else:
                    author_id = next(iter(authors_seen))
                    author_msgs: list[str] = []
                    author_name = None
                    for msg in messages:
                        if msg.author.bot or msg.author.id != author_id:
                            continue
                        content = (msg.content or "").strip()
                        if not content:
                            continue
                        author_msgs.append(content)
                        if author_name is None:
                            author_name = msg.author.display_name
                    if len(author_msgs) >= 2:
                        lines = [f"- {msg}" for msg in author_msgs[:5]]
                        combined_content = (
                            "One user sent multiple messages quickly. Reply in ONE message and cover each item. "
                            "Do not split into multiple messages.\n"
                            f"User: {author_name or 'unknown'}\n"
                            "Messages:\n" + "\n".join(lines)
                        )
                        force_addressed = True
            else:
                latest_author_id = latest_message.author.id
                author_msgs = []
                author_name = latest_message.author.display_name
                for msg in messages:
                    if msg.author.bot or msg.author.id != latest_author_id:
                        continue
                    content = (msg.content or "").strip()
                    if not content:
                        continue
                    author_msgs.append(content)
                if len(author_msgs) >= 2:
                    lines = [f"- {msg}" for msg in author_msgs[:5]]
                    combined_content = (
                        "The user sent multiple messages quickly. If you respond, do it in ONE message "
                        "and cover each item.\n"
                        f"User: {author_name}\n"
                        "Messages:\n" + "\n".join(lines)
                    )
        except Exception as exc:
            logger.warning("Failed to build multi-user batch content: %s", exc)

        # Process the latest message (this will include all the context from history)
        await self._handle_single_message(
            latest_message,
            user_content_override=combined_content,
            force_addressed=force_addressed,
        )

    async def on_message(self, message: discord.Message):
        """
        Entry point for all messages. Batches messages that arrive quickly
        and processes them together.
        """
        if message.author.bot or not self.settings.is_channel_allowed(message.channel.id):
            return
        if self.user and message.author.id == self.user.id:
            return

        # Spam protection
        if self.settings.enable_spam_protection:
            channel_id = message.channel.id
            user_id = message.author.id
            now = time.time()
            key = (channel_id, user_id)

            # Initialize timestamps list if not exists
            if key not in self.user_message_timestamps:
                self.user_message_timestamps[key] = []

            # Remove timestamps older than the time window
            self.user_message_timestamps[key] = [
                ts for ts in self.user_message_timestamps[key]
                if now - ts < self.settings.spam_time_window
            ]

            # Add current timestamp
            self.user_message_timestamps[key].append(now)

            # Check if user exceeded rate limit
            if len(self.user_message_timestamps[key]) > self.settings.spam_rate_limit:
                logger.warning(
                    f"Spam detected: User {message.author.name} ({user_id}) exceeded rate limit "
                    f"({len(self.user_message_timestamps[key])} messages in {self.settings.spam_time_window}s)"
                )
                try:
                    await message.delete()
                    logger.info(f"Deleted spam message from {message.author.name}")
                except discord.errors.Forbidden:
                    logger.warning(f"Missing permissions to delete message from {message.author.name}")
                except Exception as e:
                    logger.error(f"Error deleting spam message: {e}")
                return

        # Security check - block malicious content
        if self.async_security:
            try:
                security_result = await self.async_security.process_discord_message_async(
                    content=message.content,
                    author_name=message.author.name,
                    author_id=str(message.author.id),
                    channel_id=str(message.channel.id)
                )

                if not security_result.is_safe:
                    logger.warning(
                        f"SECURITY BLOCK: Message from {message.author.name} blocked - "
                        f"Threat: {security_result.threat_type}, "
                        f"Details: {security_result.details[:100]}"
                    )
                    # Optionally notify user (be careful not to leak attack details)
                    try:
                        await message.add_reaction("⚠️")
                    except:
                        pass
                    return

                # Use sanitized content if available
                if security_result.sanitized_content and security_result.sanitized_content != message.content:
                    logger.info(f"Content sanitized for {message.author.name}")
                    # Note: We can't modify the Discord message object, but we'll use sanitized
                    # content when storing in memory below
            except Exception as e:
                logger.error(f"Security check error: {e} - Allowing message through")

        channel_id = message.channel.id

        # Add message to pending batch
        if channel_id not in self.pending_messages:
            self.pending_messages[channel_id] = []
        self.pending_messages[channel_id].append(message)

        # Cancel existing timer if there is one
        if channel_id in self.batch_timers:
            self.batch_timers[channel_id].cancel()

        # Create new timer to process the batch
        async def process_after_delay():
            await asyncio.sleep(self.batch_window_seconds)
            await self._process_batched_messages(channel_id)

        self.batch_timers[channel_id] = asyncio.create_task(process_after_delay())

    async def _handle_single_message(
        self,
        message: discord.Message,
        user_content_override: Optional[str] = None,
        suppress_text_reply: bool = False,
        force_addressed: bool = False,
    ):
        """
        Process a single message (may represent multiple user messages).
        This is the main message processing logic.
        """
        if message.author.bot or not self.settings.is_channel_allowed(message.channel.id):
            return
        if self.user and message.author.id == self.user.id:
            return

        original_content = (message.content or "").strip()
        clean_content = (user_content_override or original_content).strip()

        audio_transcripts: list[str] = []
        if self.settings.elevenlabs_stt_enabled and self.elevenlabs_client:
            audio_transcripts = await self._transcribe_audio_attachments(message.attachments)
            if audio_transcripts:
                transcript_block = "\n".join(f"- {t}" for t in audio_transcripts)
                if clean_content:
                    clean_content = f"{clean_content}\n[Audio transcripts]\n{transcript_block}"
                else:
                    clean_content = f"[Audio transcripts]\n{transcript_block}"
        lower_content = clean_content.lower()
        has_image_attachment = any(
            _attachment_looks_like_image(attachment) for attachment in message.attachments
        )

        # Sanitize content for logging to prevent log injection
        try:
            from security.comprehensive_sanitization import ComprehensiveSanitizer
            safe_log_content = ComprehensiveSanitizer.sanitize_for_logging(clean_content, max_length=120)
        except ImportError:
            # Fallback to basic sanitization
            safe_log_content = clean_content.replace("\n", "\\n")[:120]

        logger.info(
            "RX message channel=%s author=%s content=%s",
            message.channel.id,
            message.author,
            safe_log_content,
        )

        # Load state
        global_state = await self.state_manager.ensure_global_state()
        global_state = await self._ensure_biological_state_loaded(global_state)
        channel_state = await self.state_manager.get_channel_state(str(message.channel.id))
        user_state = await self.state_manager.get_user_state(str(message.author.id), message.author.name)
        now = dt.datetime.now(tz=dt.timezone.utc)
        user_state.last_seen_at = now
        user_state.last_channel_id = str(message.channel.id)

        # Track if the user replied directly to Sel (even without a mention)
        is_reply_to_sel = False
        is_reply_to_other = False
        if message.reference:
            resolved = message.reference.resolved or getattr(message.reference, "cached_message", None)
            if resolved and resolved.author and self.user and resolved.author.id == self.user.id:
                is_reply_to_sel = True
            elif resolved and resolved.author:
                is_reply_to_other = True
            elif message.reference.message_id and self.user:
                try:
                    ref_msg = await message.channel.fetch_message(message.reference.message_id)
                    is_reply_to_sel = ref_msg.author.id == self.user.id
                    if not is_reply_to_sel:
                        is_reply_to_other = True
                except Exception:
                    pass

        # Classify message and update hormones
        classification = await self.llm_client.classify_message(clean_content or "")
        sentiment = str(classification.get("sentiment", "neutral"))
        intensity = float(classification.get("intensity", 0.3) or 0.3)
        playful = bool(classification.get("playful", False))

        bio_effects: dict[str, float] = {}
        goal_effects: dict[str, float] = {}
        bio_bond_level: Optional[float] = None
        async with self._bio_lock:
            self.biological_state.last_activity_ts = now
            self.biological_state.last_activity_channel_id = str(message.channel.id)
            if user_state and str(message.author.id) not in self.biological_state.bonding.user_bonds:
                self.biological_state.bonding.user_bonds[str(message.author.id)] = user_state.bond
            bio_effects = self.biological_state.process_message(
                clean_content,
                str(message.author.id),
                sentiment,
                intensity,
            )
            if sentiment != "negative" and (
                _looks_like_goal_completion(clean_content) or _looks_like_gratitude(clean_content)
            ):
                goal_effects = self.biological_state.goals.help_user_complete_task()
            bio_bond_level = self.biological_state.bonding.get_bond_level(str(message.author.id))
            self._bio_dirty = True

        if self.hormone_manager:
            # HIM-based hormone storage (global mood = same state for all channels)
            mood_id = self._get_mood_id(str(message.channel.id))
            cached = await self.hormone_manager.get_state(mood_id)
            pre_hormones = cached.vector
            logger.info(
                "Classification channel=%s sentiment=%s intensity=%s playful=%s memory=%s state_before=%s",
                message.channel.id,
                sentiment,
                intensity,
                playful,
                classification.get("memory_write"),
                pre_hormones.natural_language_summary(),
            )

            # Apply message effects to hormone vector
            hormones = apply_message_effects(
                cached.vector,
                sentiment=sentiment,
                intensity=intensity,
                playful=playful,
            )
            if bio_effects or goal_effects:
                hormones.apply(_merge_effects(bio_effects, goal_effects))

            # Update HormoneStateManager cache (global mood)
            await self.hormone_manager.update_state(
                mood_id,
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
                sentiment,
                intensity,
                playful,
                classification.get("memory_write"),
                pre_hormones.natural_language_summary(),
            )
            hormones = HormoneVector.from_channel(channel_state)
            hormones = apply_message_effects(
                hormones,
                sentiment=sentiment,
                intensity=intensity,
                playful=playful,
            )
            if bio_effects or goal_effects:
                hormones.apply(_merge_effects(bio_effects, goal_effects))
            hormones.to_channel(channel_state)
            await self.state_manager.update_channel_state(channel_state)
            logger.info(
                "State after message channel=%s mood=%s",
                message.channel.id,
                hormones.natural_language_summary(),
            )

        # Update per-user feelings
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

        if bio_bond_level is not None:
            user_state.bond = _clamp((user_state.bond * 0.7) + (bio_bond_level * 0.3))

        if global_delta:
            await self.self_improvement.apply_bounded_adjustments(
                global_state,
                reason=f"feedback:{sentiment}",
                delta=global_delta,
            )

        # Optionally write memory (global memory = SEL remembers across ALL channels)
        if classification.get("memory_write") or len(clean_content.strip()) >= 20:
            channel_name = getattr(message.channel, 'name', 'DM')
            if self.settings.memory_summarize_enabled:
                summary = await self.llm_client.summarize_for_memory(
                    message.author.display_name,
                    clean_content or "User sent an attachment.",
                )
                if not summary:
                    summary = None  # SKIP — don't store trivial message
            else:
                raw_content = clean_content
                if not raw_content:
                    if has_image_attachment:
                        raw_content = "User shared images."
                    else:
                        raw_content = "User shared an attachment or non-text message."
                summary = f"[{channel_name}] {message.author.display_name}: {raw_content}"[:400]
            if summary:
                salience = float(classification.get("intensity", 0.5))
                memory_id = self._get_memory_id(str(message.channel.id))
                await self.memory_manager.maybe_store(
                    channel_id=memory_id,
                    summary=summary,
                    tags=["user_message", f"channel:{channel_name}", f"user:{message.author.display_name}"],
                    salience=salience,
                )
                logger.info("Stored memory summary=%s", summary[:80])

        bot_name = self.user.name if self.user else "sel"
        name_called = _name_called(lower_content, bot_name)
        misnamed = " cel" in lower_content or lower_content.startswith("cel") or "her name is cel" in lower_content
        is_voice_message = bool(getattr(message, "is_voice_message", False))
        is_mentioned = (self.user in message.mentions if self.user else False) or is_reply_to_sel or is_voice_message
        addressed_to_sel = is_mentioned or name_called or force_addressed
        direct_question = is_direct_question_to_sel(clean_content, bot_name) or (
            "?" in clean_content and (is_reply_to_sel or force_addressed)
        )
        other_mentions = []
        if message.mentions:
            other_mentions = [
                member for member in message.mentions if not self.user or member.id != self.user.id
            ]
        greeting_target = extract_greeting_target(clean_content)
        greeting_to_other = (
            greeting_target is not None
            and greeting_target != bot_name.strip().lower()
            and not is_broadcast_greeting_target(greeting_target)
        )
        addressed_to_other = (not addressed_to_sel) and (
            is_reply_to_other or bool(other_mentions) or greeting_to_other
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

        # Check for voice channel commands
        command_text = lower_content.strip()
        if command_text in ("sel join", "sel join vc", "sel join voice", "sel join here", "sel join me"):
            await self._handle_voice_join_author(message)
            return

        if command_text.startswith("sel join "):
            join_arg = clean_content[9:].strip()
            if not join_arg:
                await self._handle_voice_join_author(message)
                return
            join_arg_lower = join_arg.lower()
            if join_arg_lower in ("me", "here", "vc", "voice", "voicechat", "voice channel"):
                await self._handle_voice_join_author(message)
                return
            channel_id = _extract_channel_id(join_arg)
            if channel_id is not None:
                await self._handle_voice_join_by_id(message, channel_id)
                return
            if message.guild:
                channel = _find_voice_channel_by_name(message.guild, join_arg)
                if channel:
                    await self._handle_voice_join_channel(message, channel)
                    return
            await message.channel.send(
                "Couldn't find that voice channel. Try `sel join` while you're in VC, "
                "or `sel join <#channel>` / `sel join <channel_id>`."
            )
            return

        if command_text == "sel follow":
            await message.channel.send("Please provide a user mention or ID: `sel follow @user`")
            return

        if command_text.startswith("sel follow "):
            follow_arg = clean_content[11:].strip()
            if follow_arg.lower() in ("me", "myself"):
                await self._handle_voice_follow_user(message, message.author.id)
                return
            user_id = _extract_user_id(follow_arg)
            if user_id is not None:
                await self._handle_voice_follow_user(message, user_id)
                return
            await message.channel.send("Please provide a valid user mention or ID: `sel follow @user`")
            return

        if self.settings.voice_leave_phrases:
            if any(phrase in lower_content for phrase in self.settings.voice_leave_phrases):
                await self._handle_voice_leave(message)
                return

        if command_text in ("sel leave", "sel leave vc", "sel leave voice"):
            await self._handle_voice_leave(message)
            return

        if command_text == "sel unfollow":
            self.following_user_id = None
            await message.channel.send("No longer following anyone in voice channels.")
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
                if self._bio_dirty:
                    async with self._bio_lock:
                        if self._bio_dirty:
                            global_state.biological_state = self.biological_state.to_dict()
                            self._bio_dirty = False
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
                confidence_score=None,
            )
            if suggestions:
                await self._dm_approver_suggestions(suggestions, context_preview=clean_content[:160])
            return

        # Gather recent context first for decision-making
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
                    time_str = _format_relative_time(msg.created_at)
                    recent_msgs.append(f"[{time_str}] {msg.author.display_name}{marker}: {snippet}")
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

        # Add Discord presence context
        if message.guild:
            presence_context = self.presence_tracker.get_context_for_prompt(message.guild, limit=5)
            if channel_dynamics:
                channel_dynamics += "\n" + presence_context
            else:
                channel_dynamics = presence_context

        # Human-like engagement decision using LLM
        # Always respond if explicitly addressed or asked directly
        if addressed_to_other and not addressed_to_sel:
            should_reply = False
        elif addressed_to_sel or direct_question:
            should_reply = True
        else:
            # Let the LLM decide based on conversation context and mood
            should_reply = await self.llm_client.should_engage_naturally(
                recent_conversation=recent_context[:2000] if recent_context else "",
                user_message=clean_content,
                mood_summary=hormones.natural_language_summary(),
                is_continuation=continuation_hit
            )

        if not should_reply:
            channel_state.messages_since_response += 1
            await self.state_manager.update_channel_state(channel_state)
            async with self.state_manager.session() as session:
                if self._bio_dirty:
                    async with self._bio_lock:
                        if self._bio_dirty:
                            global_state.biological_state = self.biological_state.to_dict()
                            self._bio_dirty = False
                await session.merge(global_state)
                await session.merge(user_state)
                await session.commit()
            reason = "addressed_to_other" if addressed_to_other and not addressed_to_sel else "engagement"
            logger.info(
                "Decision: silent channel=%s reason=%s ms_since=%s secs_since=%s cortisol=%.2f melatonin=%.2f novelty=%.2f",
                message.channel.id,
                reason,
                channel_state.messages_since_response,
                seconds_since_response,
                hormones.cortisol,
                hormones.melatonin,
                hormones.novelty,
            )
            # If she's disengaging from an active conversation (not just ignoring unrelated chat),
            # send "..." so it reads as intentional rather than a bot glitch
            if reason == "engagement" and continuation_hit:
                try:
                    await message.channel.send("...")
                except Exception:
                    pass
            return

        if global_state.responses_paused and not self._is_admin(message.author.id):
            channel_state.messages_since_response += 1
            await self.state_manager.update_channel_state(channel_state)
            async with self.state_manager.session() as session:
                if self._bio_dirty:
                    async with self._bio_lock:
                        if self._bio_dirty:
                            global_state.biological_state = self.biological_state.to_dict()
                            self._bio_dirty = False
                await session.merge(global_state)
                await session.merge(user_state)
                await session.commit()
            logger.info("Responses paused; skipping reply channel=%s", message.channel.id)
            return

        # Show typing immediately — fires before memory retrieval, image analysis, LLM call
        _typing_task: asyncio.Task = asyncio.create_task(_keepalive_typing(message.channel))

        # Use user's message directly for memory query (don't pollute with recent context)
        # Global memory = SEL remembers across ALL channels like a real person
        memory_id = self._get_memory_id(str(message.channel.id))
        memory_query = clean_content
        semantic_mems = await self.memory_manager.retrieve(
            memory_id, memory_query, limit=self.settings.memory_recall_limit
        )
        _recent_count = max(5, self.settings.memory_recall_limit // 5)
        _recent_mems = await self.memory_manager.retrieve_recent(memory_id, limit=_recent_count)
        _seen_sums = {m.summary for m in semantic_mems}
        memories = semantic_mems + [m for m in _recent_mems if m.summary not in _seen_sums]
        # Debug: Log retrieved memories
        logger.info(f"Retrieved {len(memories)} memories for query: '{memory_query[:100]}'")
        if memories:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            for i, mem in enumerate(memories[:3], 1):
                age_days = (now - mem.timestamp).days if mem.timestamp else 0
                logger.info(f"  Memory {i}: [{age_days}d old] {mem.summary[:80]}")
        else:
            logger.warning("No memories retrieved! Check HIM database path and contents.")

        memory_effects = _memory_mood_effects(memories)
        if memory_effects:
            hormones.apply(memory_effects)
            if self.hormone_manager:
                mood_id = self._get_mood_id(str(message.channel.id))
                await self.hormone_manager.update_state(
                    mood_id,
                    hormones,
                    focus_topic=channel_state.focus_topic,
                    energy_level=channel_state.energy_level,
                    messages_since_response=channel_state.messages_since_response,
                    last_response_ts=channel_state.last_response_ts,
                )
            else:
                hormones.to_channel(channel_state)
                await self.state_manager.update_channel_state(channel_state)
            logger.info(
                "Applied memory mood effects channel=%s effects=%s",
                message.channel.id,
                memory_effects,
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
        image_sources: list[tuple[str, Optional[str], str]] = []
        seen_urls: set[str] = set()

        for attachment in message.attachments:
            if not _attachment_looks_like_image(attachment):
                continue
            url = attachment.url
            if not url or url in seen_urls:
                continue
            image_sources.append((url, normalize_content_type(attachment.content_type), "attachment"))
            seen_urls.add(url)

        for embed in message.embeds:
            for url in _extract_embed_image_urls(embed):
                if not url or url in seen_urls:
                    continue
                if not looks_like_image_url(url):
                    continue
                image_sources.append((url, None, "embed"))
                seen_urls.add(url)

        for sticker in message.stickers:
            url = getattr(sticker, "url", None)
            if not url or url in seen_urls:
                continue
            if not looks_like_image_url(url):
                continue
            image_sources.append((url, _sticker_content_type(sticker), "sticker"))
            seen_urls.add(url)

        for url, content_type, source in image_sources:
            try:
                # Check if it's a GIF
                if self.gif_analyzer.is_gif(url, content_type):
                    logger.info("Analyzing animated GIF: %s source=%s", url, source)
                    caption = await self.gif_analyzer.analyze_gif(
                        url,
                        self.llm_client,
                        describe_prompt="Describe what you see in this frame."
                    )
                    if caption:
                        image_descriptions.append(caption)
                        logger.info(
                            "GIF analyzed for channel=%s frames_described=%s source=%s",
                            message.channel.id,
                            caption.count("Frame"),
                            source,
                        )
                    else:
                        logger.warning("Failed to analyze GIF %s source=%s", url, source)
                else:
                    # Regular static image
                    analysis = await self.llm_client.analyze_image(
                        url,
                        prompt="Describe this image for conversational context with precise, literal details.",
                    )

                    # Extract any text from the image using OCR and override if present
                    ocr_text = await self.llm_client.extract_text_from_image(url)
                    if ocr_text:
                        analysis = apply_text_override(analysis, ocr_text)

                    caption = render_vision_analysis(analysis)
                    if caption:
                        image_descriptions.append(caption)
                        logger.info(
                            "Image analyzed for channel=%s image_url=%s caption=%s source=%s",
                            message.channel.id,
                            url,
                            caption[:160],
                            source,
                        )
                    else:
                        logger.warning(
                            "Empty vision analysis for channel=%s image_url=%s source=%s",
                            message.channel.id,
                            url,
                            source,
                        )
            except Exception as exc:
                logger.warning("Failed to describe image/GIF %s source=%s: %s", url, source, exc)

        if image_descriptions:
            media_effects = _media_mood_effects(image_descriptions)
            if media_effects:
                hormones.apply(media_effects)
                if self.hormone_manager:
                    mood_id = self._get_mood_id(str(message.channel.id))
                    await self.hormone_manager.update_state(
                        mood_id,
                        hormones,
                        focus_topic=channel_state.focus_topic,
                        energy_level=channel_state.energy_level,
                        messages_since_response=channel_state.messages_since_response,
                        last_response_ts=channel_state.last_response_ts,
                    )
                else:
                    hormones.to_channel(channel_state)
                    await self.state_manager.update_channel_state(channel_state)
                logger.info(
                    "Applied media mood effects channel=%s effects=%s",
                    message.channel.id,
                    media_effects,
                )
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

        # Feature flag: use configured prompt variant for this channel
        build_messages, prompt_variant = self._select_prompt_builder(str(message.channel.id))
        logger.info(
            "Prompt variant %s selected for channel=%s user_message=%s",
            prompt_variant,
            message.channel.id,
            message.id,
        )

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
        reply = _add_human_touches(reply, hormones)
        latency_ms = int((time.perf_counter() - start) * 1000)
        reply_text = (reply or "").strip() or "(no response)"

        # Assess response confidence
        confidence_assessment = self.confidence_scorer.assess_response_confidence(
            user_query=clean_content,
            sel_response=reply_text,
            memories_count=len(memories),
            context=channel_dynamics
        )
        logger.info(
            "Response confidence channel=%s score=%d level=%s factors=%s",
            message.channel.id,
            confidence_assessment["score"],
            confidence_assessment["level"],
            confidence_assessment["factors"]
        )

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
        # Cancel typing keepalive — reply is about to be sent
        _typing_task.cancel()
        await asyncio.gather(_typing_task, return_exceptions=True)
        sent_msg: Optional[discord.Message] = None
        effective_suppress = suppress_text_reply or self.settings.voice_only_responses
        if effective_suppress:
            await asyncio.sleep(delay)
        else:
            try:
                await asyncio.sleep(delay)
                sent_msg = await message.reply(reply_text, mention_author=False)
            except Exception as exc:
                logger.warning("Failed to send reply in channel %s: %s", message.channel.id, exc)
                return
        if message.guild and message.guild.voice_client and message.guild.voice_client.is_connected():
            self.voice_announce_channel_ids[message.guild.id] = message.channel.id
        await self._maybe_queue_tts(message, reply_text)

        global_state.total_messages_sent += 1
        channel_state.last_response_ts = now
        channel_state.messages_since_response = 0
        async with self.state_manager.session() as session:
            if self._bio_dirty:
                async with self._bio_lock:
                    if self._bio_dirty:
                        global_state.biological_state = self.biological_state.to_dict()
                        self._bio_dirty = False
            await session.merge(global_state)
            await session.merge(channel_state)
            await session.merge(user_state)
            await session.commit()

        # Track feedback base event
        if sent_msg is not None:
            await self.state_manager.log_feedback(
                sel_message_id=str(sent_msg.id),
                channel_id=str(message.channel.id),
                user_id=str(message.author.id),
                latency_ms=latency_ms,
                sentiment=classification.get("sentiment", "neutral"),
                confidence_score=int(confidence_assessment["score"]),
            )
            logger.info(
                "Replied channel=%s latency_ms=%s msg_id=%s",
                message.channel.id,
                latency_ms,
                sent_msg.id,
            )
            asyncio.create_task(self.seal_editor.on_interaction(
                channel_id=str(message.channel.id),
                memory_id=memory_id,
                user_state=user_state,
                global_state=global_state,
                classification=classification,
            ))

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

    def _get_self_member(self, guild: discord.Guild) -> Optional[discord.Member]:
        if guild.me:
            return guild.me
        if self.user:
            return guild.get_member(self.user.id)
        return None

    async def _connect_to_voice_channel(
        self,
        guild: discord.Guild,
        channel: discord.abc.GuildChannel,
        announce_channel: Optional[discord.abc.Messageable] = None,
    ) -> bool:
        if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
            if announce_channel:
                await announce_channel.send(f"Channel {channel.id} is not a voice channel")
            return False

        me = self._get_self_member(guild)
        speak_warning = None
        if me:
            perms = channel.permissions_for(me)
            if not perms.connect:
                if announce_channel:
                    await announce_channel.send("I don't have permission to connect to that voice channel.")
                else:
                    logger.warning(
                        "Missing Connect permission for voice channel %s (%s)",
                        channel.name,
                        channel.id,
                    )
                return False
            if not perms.speak:
                speak_warning = "I don't have Speak permission here, so TTS won't play."

        voice_client = guild.voice_client
        if voice_client and voice_client.is_connected():
            if voice_client.channel and voice_client.channel.id == channel.id:
                if announce_channel:
                    await announce_channel.send(f"Already in voice channel: {channel.name}")
                self._start_voice_listening(voice_client)
                return True
            await voice_client.disconnect()

        try:
            connect_kwargs: dict[str, object] = {"self_deaf": False}
            if self._can_listen_to_voice() and VOICE_RECV_AVAILABLE:
                connect_kwargs["cls"] = voice_recv.VoiceRecvClient
            voice_client = await channel.connect(**connect_kwargs)
            self._start_voice_listening(voice_client)
            if isinstance(channel, discord.StageChannel):
                try:
                    await channel.request_to_speak()
                except Exception as exc:
                    logger.warning(
                        "Failed to request to speak in stage channel %s: %s",
                        channel.id,
                        exc,
                    )
            if announce_channel:
                if speak_warning:
                    await announce_channel.send(f"Joined voice channel: {channel.name}. {speak_warning}")
                else:
                    await announce_channel.send(f"Joined voice channel: {channel.name}")
            logger.info("Joined voice channel %s (ID: %s)", channel.name, channel.id)
            if speak_warning and not announce_channel:
                logger.warning("Joined voice channel %s but missing Speak permission.", channel.name)
            return True
        except Exception as exc:
            logger.error("Failed to join voice channel %s: %s", channel.id, exc)
            if announce_channel:
                await announce_channel.send(f"Failed to join voice channel: {exc}")
            return False

    async def _handle_voice_join_channel(
        self,
        message: discord.Message,
        channel: discord.abc.GuildChannel,
    ) -> None:
        if not message.guild:
            await message.channel.send("Voice commands only work in servers.")
            return
        if channel.guild.id != message.guild.id:
            await message.channel.send("That voice channel isn't in this server.")
            return
        success = await self._connect_to_voice_channel(message.guild, channel, announce_channel=message.channel)
        if success:
            self.voice_announce_channel_ids[message.guild.id] = message.channel.id

    async def _handle_voice_join_author(self, message: discord.Message) -> None:
        if not message.guild:
            await message.channel.send("Voice commands only work in servers.")
            return
        voice_state = getattr(message.author, "voice", None)
        if not voice_state or not voice_state.channel:
            await message.channel.send("Join a voice channel first, or use `sel join <#channel>`.")
            return
        await self._handle_voice_join_channel(message, voice_state.channel)

    async def _announce_voice_event(self, guild_id: int, content: str) -> None:
        channel_id = self.voice_announce_channel_ids.get(guild_id)
        if not channel_id:
            return
        if not self.settings.is_channel_allowed(channel_id):
            return
        channel = self.get_channel(channel_id)
        if not channel or not hasattr(channel, "send"):
            return
        try:
            await channel.send(content)
        except Exception as exc:
            logger.warning("Failed to announce voice event in channel %s: %s", channel_id, exc)

    async def _disconnect_voice(
        self,
        guild: discord.Guild,
        reason: Optional[str] = None,
        *,
        announce: bool = True,
    ) -> bool:
        voice_client = guild.voice_client
        if not voice_client or not voice_client.is_connected():
            return False
        try:
            await voice_client.disconnect()
            self.voice_sinks.pop(guild.id, None)
            if announce:
                if reason:
                    await self._announce_voice_event(guild.id, f"Left voice channel ({reason}).")
                else:
                    await self._announce_voice_event(guild.id, "Left voice channel.")
            return True
        except Exception as exc:
            logger.warning("Failed to disconnect from voice in guild %s: %s", guild.id, exc)
            return False

    def _can_listen_to_voice(self) -> bool:
        return (
            self.settings.voice_stt_enabled
            and self.settings.elevenlabs_stt_enabled
            and self.elevenlabs_client is not None
        )

    def _start_voice_listening(self, voice_client: discord.VoiceClient) -> None:
        if not self._can_listen_to_voice():
            return
        if not VOICE_RECV_AVAILABLE:
            logger.warning("VOICE_STT_ENABLED is true but discord-ext-voice-recv is not installed.")
            return
        if not hasattr(voice_client, "listen"):
            logger.warning("Voice client does not support receive; upgrade discord-ext-voice-recv.")
            return
        if getattr(voice_client, "is_listening", lambda: False)():
            return
        sink = VoiceTranscriptionSink(
            self,
            sample_rate=self.settings.voice_stt_sample_rate,
            channels=self.settings.voice_stt_channels,
            min_seconds=self.settings.voice_stt_min_seconds,
            max_seconds=self.settings.voice_stt_max_seconds,
        )
        self.voice_sinks[voice_client.guild.id] = sink

        def _after_listen(exc: Optional[BaseException] = None) -> None:
            if exc:
                logger.warning("Voice receive stopped with error: %s", exc)
            self.voice_sinks.pop(voice_client.guild.id, None)
            if exc:
                now = time.time()
                last = self.voice_listen_restart_at.get(voice_client.guild.id, 0.0)
                if now - last < 5.0:
                    return
                self.voice_listen_restart_at[voice_client.guild.id] = now
                try:
                    self.loop.call_soon_threadsafe(
                        lambda: asyncio.create_task(
                            self._restart_voice_listening(voice_client.guild.id)
                        )
                    )
                except Exception as restart_exc:
                    logger.warning(
                        "Failed to schedule voice receive restart for guild %s: %s",
                        voice_client.guild.id,
                        restart_exc,
                    )

        try:
            voice_client.listen(sink, after=_after_listen)
            logger.info("Voice receive started in guild %s", voice_client.guild.id)
        except Exception as exc:
            logger.warning("Failed to start voice receive in guild %s: %s", voice_client.guild.id, exc)
            self.voice_sinks.pop(voice_client.guild.id, None)

    async def _restart_voice_listening(self, guild_id: int) -> None:
        await asyncio.sleep(1.0)
        guild = self.get_guild(guild_id)
        if not guild:
            return
        voice_client = guild.voice_client
        if not voice_client or not voice_client.is_connected():
            return
        self._start_voice_listening(voice_client)

    async def _handle_voice_pcm(self, member: discord.Member, pcm_bytes: bytes) -> None:
        if not self._can_listen_to_voice():
            return
        if not member or member.bot:
            return
        guild = member.guild
        if not guild:
            return
        channel_id = self.voice_announce_channel_ids.get(guild.id)
        if not channel_id:
            return
        if not self.settings.is_channel_allowed(channel_id):
            return
        channel = self.get_channel(channel_id)
        if not channel or not hasattr(channel, "send"):
            return
        try:
            wav_bytes = _pcm_to_wav_bytes(
                pcm_bytes,
                sample_rate=self.settings.voice_stt_sample_rate,
                channels=self.settings.voice_stt_channels,
            )
            result = await self.elevenlabs_client.transcribe(
                audio_bytes=wav_bytes,
                filename="voice.wav",
                model_id=self.settings.elevenlabs_stt_model,
                language_code=self.settings.elevenlabs_stt_language_code or None,
                content_type="audio/wav",
                enable_logging=self.settings.elevenlabs_stt_enable_logging,
            )
            text = (
                (result.get("text") if isinstance(result, dict) else None)
                or (result.get("transcript") if isinstance(result, dict) else None)
                or (result.get("transcription") if isinstance(result, dict) else None)
            )
            if not text:
                return
            transcript = str(text).strip()
            if not transcript:
                return
            if self.settings.voice_stt_post_transcripts:
                await channel.send(f"**{member.display_name} (voice):** {transcript}")
            if self.settings.voice_stt_auto_respond:
                proxy = VoiceMessageProxy(
                    author=member,
                    channel=channel,
                    guild=guild,
                    content=transcript,
                )
                await self._handle_single_message(
                    proxy,
                    suppress_text_reply=self.settings.voice_stt_silent_text,
                )
        except Exception as exc:
            logger.warning("Voice transcription failed for %s: %s", member, exc)

    async def _get_voice_hormones(self, guild_id: int) -> Optional[HormoneVector]:
        channel_id = self.voice_announce_channel_ids.get(guild_id)
        if self.hormone_manager:
            mood_id = self._get_mood_id(str(channel_id or guild_id))
            cached = await self.hormone_manager.get_state(mood_id)
            return cached.vector
        if channel_id is None:
            return None
        channel_state = await self.state_manager.get_channel_state(str(channel_id))
        return HormoneVector.from_channel(channel_state)

    def _hormone_leave_reason(self, hormones: HormoneVector) -> Optional[str]:
        checks: list[bool] = []
        melatonin_min = self.settings.voice_auto_leave_melatonin_min
        dopamine_max = self.settings.voice_auto_leave_dopamine_max
        if melatonin_min is not None:
            checks.append(hormones.melatonin >= melatonin_min)
        if dopamine_max is not None:
            checks.append(hormones.dopamine <= dopamine_max)
        if not checks:
            return None
        if all(checks):
            return "Feeling sleepy/low energy"
        return None

    async def _voice_auto_leave_loop(self) -> None:
        interval = max(5, self.settings.voice_auto_leave_check_seconds)
        empty_minutes = max(0.1, self.settings.voice_auto_leave_empty_minutes)
        while True:
            try:
                await asyncio.sleep(interval)
                now = dt.datetime.now(tz=dt.timezone.utc)
                for guild in self.guilds:
                    voice_client = guild.voice_client
                    if not voice_client or not voice_client.is_connected():
                        self.voice_empty_since.pop(guild.id, None)
                        continue
                    channel = voice_client.channel
                    if not channel:
                        continue

                    humans = [member for member in channel.members if not member.bot]
                    if not humans:
                        empty_since = self.voice_empty_since.get(guild.id)
                        if not empty_since:
                            self.voice_empty_since[guild.id] = now
                        else:
                            elapsed = (now - empty_since).total_seconds()
                            if elapsed >= empty_minutes * 60:
                                await self._disconnect_voice(
                                    guild,
                                    reason=f"No one else in voice for {empty_minutes:.0f}m",
                                    announce=False,
                                )
                                self.voice_empty_since.pop(guild.id, None)
                                continue
                    else:
                        self.voice_empty_since.pop(guild.id, None)

                    if self.settings.voice_auto_leave_hormone_enabled:
                        hormones = await self._get_voice_hormones(guild.id)
                        if hormones:
                            reason = self._hormone_leave_reason(hormones)
                            if reason:
                                await self._disconnect_voice(guild, reason=reason, announce=False)
                                self.voice_empty_since.pop(guild.id, None)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Voice auto-leave loop error: %s", exc)

    async def _handle_voice_join_by_id(self, message: discord.Message, channel_id: int) -> None:
        """Join a voice channel by its ID."""
        try:
            if not message.guild:
                await message.channel.send("Voice commands only work in servers.")
                return
            channel = message.guild.get_channel(channel_id)
            if not channel:
                await message.channel.send(f"Could not find channel with ID {channel_id}")
                return
            await self._handle_voice_join_channel(message, channel)
        except Exception as exc:
            logger.error("Failed to join voice channel %s: %s", channel_id, exc)
            await message.channel.send(f"Failed to join voice channel: {exc}")

    async def _handle_voice_follow_user(self, message: discord.Message, user_id: int) -> None:
        """Follow a user through voice channels."""
        try:
            if not message.guild:
                await message.channel.send("Voice commands only work in servers.")
                return
            guild = message.guild
            member = guild.get_member(user_id)
            if not member:
                try:
                    member = await guild.fetch_member(user_id)
                except Exception:
                    member = None
            if not member:
                await message.channel.send(f"Could not find user with ID {user_id} in this server")
                return

            self.following_user_id = user_id
            await message.channel.send(f"Now following {member.display_name} through voice channels")
            logger.info("Now following user %s (ID: %s)", member.display_name, user_id)
            self.voice_announce_channel_ids[guild.id] = message.channel.id

            # Check if user is already in a voice channel and join them
            if member.voice and member.voice.channel:
                await self._connect_to_voice_channel(guild, member.voice.channel, announce_channel=message.channel)

        except Exception as exc:
            logger.error("Failed to follow user %s: %s", user_id, exc)
            await message.channel.send(f"Failed to follow user: {exc}")

    async def _handle_voice_leave(self, message: discord.Message) -> None:
        """Leave the current voice channel."""
        try:
            if message.guild and message.guild.voice_client:
                await message.guild.voice_client.disconnect()
                await message.channel.send("Left voice channel")
                logger.info("Left voice channel")
                self.voice_sinks.pop(message.guild.id, None)
                self.voice_empty_since.pop(message.guild.id, None)
            else:
                await message.channel.send("Not in a voice channel")
        except Exception as exc:
            logger.error(f"Failed to leave voice channel: {exc}")
            await message.channel.send(f"Failed to leave voice channel: {exc}")

    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState
    ) -> None:
        """Track voice state updates to follow users."""
        if not self.following_user_id or member.id != self.following_user_id:
            return

        try:
            # User joined a voice channel
            if after.channel and before.channel != after.channel:
                await self._connect_to_voice_channel(member.guild, after.channel)
                logger.info("Following %s to voice channel %s", member.name, after.channel.name)

            # User left voice channel
            elif not after.channel and before.channel:
                if member.guild.voice_client:
                    await member.guild.voice_client.disconnect()
                    logger.info("%s left voice, disconnecting", member.name)

        except Exception as exc:
            logger.error("Failed to follow %s: %s", member.name, exc)

    async def _cmd_status(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        global_state = await self.state_manager.ensure_global_state()
        channel_id = str(interaction.channel_id) if interaction.channel_id else "dm"

        # Get hormones from HIM or legacy storage (global mood)
        mood_id = self._get_mood_id(channel_id)
        if self.hormone_manager:
            cached = await self.hormone_manager.get_state(mood_id)
            hormones = cached.vector
            him_status = "HIM API (Global)" if self.hormone_manager.him_available else "Cache-only (Global)"
        else:
            channel_state = await self.state_manager.get_channel_state(channel_id)
            hormones = HormoneVector.from_channel(channel_state)
            him_status = "Legacy DB"

        # Get all hormone values as dict
        hormone_dict = hormones.to_dict()

        # Group hormones by category for display
        neurotransmitters = ["dopamine", "serotonin", "adrenaline", "endorphin"]
        stress_hormones = ["cortisol", "melatonin"]
        social_hormones = ["oxytocin", "estrogen", "testosterone", "progesterone"]
        emotional_states = ["anxiety", "excitement", "frustration", "contentment", "loneliness", "affection", "confidence", "confusion", "boredom", "anticipation"]
        conceptual = ["novelty", "curiosity", "patience"]

        def format_bar(value: float) -> str:
            """Create a visual bar for hormone level."""
            clamped = max(-1.0, min(1.0, value))
            # Map -1 to 1 range to 0-10 for display
            normalized = int((clamped + 1) * 5)
            return "█" * normalized + "░" * (10 - normalized)

        def format_hormone(name: str, value: float) -> str:
            bar = format_bar(value)
            sign = "+" if value >= 0 else ""
            return f"`{name:12s}` {bar} {sign}{value:.2f}"

        lines = [
            f"**Sel Status** (Channel: {channel_id[:8]}...)",
            f"**Mood:** {hormones.natural_language_summary()}",
            f"**Storage:** {him_status}",
            "",
            "**Neurotransmitters:**",
        ]
        for h in neurotransmitters:
            lines.append(format_hormone(h, hormone_dict.get(h, 0.0)))

        lines.append("\n**Stress/Sleep:**")
        for h in stress_hormones:
            lines.append(format_hormone(h, hormone_dict.get(h, 0.0)))

        lines.append("\n**Social/Hormonal:**")
        for h in social_hormones:
            lines.append(format_hormone(h, hormone_dict.get(h, 0.0)))

        lines.append("\n**Emotional States:**")
        for h in emotional_states:
            lines.append(format_hormone(h, hormone_dict.get(h, 0.0)))

        lines.append("\n**Conceptual:**")
        for h in conceptual:
            lines.append(format_hormone(h, hormone_dict.get(h, 0.0)))

        lines.append(f"\n**Global:** Teasing: {global_state.teasing_level:.2f} | Emoji: {global_state.emoji_rate:.2f} | Empathy: {global_state.empathy:.2f}")

        msg = "\n".join(lines)
        # Discord has 2000 char limit, split if needed
        if len(msg) > 1900:
            await interaction.followup.send(msg[:1900], ephemeral=True)
            await interaction.followup.send(msg[1900:], ephemeral=True)
        else:
            await interaction.followup.send(msg, ephemeral=True)

    async def _cmd_reset_mood(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        if not self._is_admin(interaction.user.id):
            await interaction.followup.send("You are not authorized to use this command.", ephemeral=True)
            return

        channel_id = str(interaction.channel_id) if interaction.channel_id else "dm"
        mood_id = self._get_mood_id(channel_id)
        vector = _baseline_hormone_vector()
        if self.hormone_manager:
            await self.hormone_manager.update_state(
                mood_id,
                vector,
                focus_topic=None,
                energy_level=0.5,
                messages_since_response=0,
                last_response_ts=None,
            )
        else:
            channel_state = await self.state_manager.get_channel_state(channel_id)
            vector.to_channel(channel_state)
            await self.state_manager.update_channel_state(channel_state)
        await interaction.followup.send("Mood reset to baseline levels.", ephemeral=True)

    async def _cmd_set_cycle_day(self, interaction: discord.Interaction, day: int) -> None:
        await interaction.response.defer(ephemeral=True)
        if not self._is_admin(interaction.user.id):
            await interaction.followup.send("You are not authorized to use this command.", ephemeral=True)
            return
        if day < 1 or day > 28:
            await interaction.followup.send("Cycle day must be between 1 and 28.", ephemeral=True)
            return
        global_state = await self._ensure_biological_state_loaded()
        async with self._bio_lock:
            now = dt.datetime.now(dt.timezone.utc)
            self.biological_state.menstrual.cycle_start_date = now - dt.timedelta(days=day - 1)
            phase = self.biological_state.menstrual.get_phase()
            self._bio_dirty = True
        async with self.state_manager.session() as session:
            global_state.biological_state = self.biological_state.to_dict()
            self._bio_dirty = False
            await session.merge(global_state)
            await session.commit()
        await interaction.followup.send(f"Cycle day set to {day} ({phase}).", ephemeral=True)

    async def _cmd_set_attachment(self, interaction: discord.Interaction, style: str) -> None:
        await interaction.response.defer(ephemeral=True)
        if not self._is_admin(interaction.user.id):
            await interaction.followup.send("You are not authorized to use this command.", ephemeral=True)
            return
        normalized = (style or "").strip().lower()
        if normalized not in {"anxious", "secure", "avoidant"}:
            await interaction.followup.send(
                "Attachment style must be one of: anxious, secure, avoidant.",
                ephemeral=True,
            )
            return
        global_state = await self._ensure_biological_state_loaded()
        async with self._bio_lock:
            self.biological_state.bonding.attachment_style = normalized
            self._bio_dirty = True
        async with self.state_manager.session() as session:
            global_state.biological_state = self.biological_state.to_dict()
            self._bio_dirty = False
            await session.merge(global_state)
            await session.commit()
        await interaction.followup.send(f"Attachment style set to {normalized}.", ephemeral=True)

    async def _cmd_debug_bio(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        if not self._is_admin(interaction.user.id):
            await interaction.followup.send("You are not authorized to use this command.", ephemeral=True)
            return
        await self._ensure_biological_state_loaded()
        async with self._bio_lock:
            cycle_day = self.biological_state.menstrual.get_cycle_day()
            phase = self.biological_state.menstrual.get_phase()
            lines = [
                f"sleep_debt_hours: {self.biological_state.sleep_debt.debt_hours:.2f}",
                f"late_nights: {self.biological_state.sleep_debt.consecutive_late_nights}",
                f"caffeine_level: {self.biological_state.caffeine.caffeine_level:.2f}",
                f"caffeine_tolerance: {self.biological_state.caffeine.tolerance:.2f}",
                f"cycle_day: {cycle_day} ({phase})",
                f"chronic_stress: {self.biological_state.stress.chronic_stress:.2f}",
                f"attachment_style: {self.biological_state.bonding.attachment_style}",
                f"last_activity_ts: {self.biological_state.last_activity_ts}",
                f"last_activity_channel: {self.biological_state.last_activity_channel_id}",
                f"daily_cortisol_avg_samples: {self.biological_state.daily_cortisol_samples}",
                f"sleep_inactive_minutes: {self.biological_state.sleep_inactive_minutes}",
            ]
        await interaction.followup.send("Bio debug:\n" + "\n".join(lines), ephemeral=True)

    async def _cmd_pause(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        if not self._is_admin(interaction.user.id):
            await interaction.followup.send("You are not authorized to use this command.", ephemeral=True)
            return
        global_state = await self.state_manager.ensure_global_state()
        global_state.responses_paused = True
        async with self.state_manager.session() as session:
            await session.merge(global_state)
            await session.commit()
        await interaction.followup.send("Sel responses are now paused.", ephemeral=True)

    async def _cmd_resume(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        if not self._is_admin(interaction.user.id):
            await interaction.followup.send("You are not authorized to use this command.", ephemeral=True)
            return
        global_state = await self.state_manager.ensure_global_state()
        global_state.responses_paused = False
        async with self.state_manager.session() as session:
            await session.merge(global_state)
            await session.commit()
        await interaction.followup.send("Sel responses resumed.", ephemeral=True)

    async def _cmd_mood_timeline(
        self,
        interaction: discord.Interaction,
        hormone: str = "dopamine",
        hours: int = 24,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        hormone_key = (hormone or "dopamine").strip().lower()
        if hormone_key not in BASELINE_LEVELS:
            await interaction.followup.send("Unknown hormone name.", ephemeral=True)
            return
        hours = max(1, min(168, hours))
        if not self.hormone_manager:
            await interaction.followup.send("Timeline requires HIM hormone storage.", ephemeral=True)
            return
        api_url = f"http://{self.settings.him_api_host}:{self.settings.him_api_port}"
        if self.settings.him_api_host == "0.0.0.0":
            api_url = f"http://127.0.0.1:{self.settings.him_api_port}"
        query = HormoneHistoryQuery(api_base_url=api_url)
        channel_id = str(interaction.channel_id) if interaction.channel_id else "dm"
        mood_id = self._get_mood_id(channel_id)
        end = dt.datetime.now(dt.timezone.utc)
        start = end - dt.timedelta(hours=hours)
        snapshots = await query.query_range(mood_id, start, end, level=0, limit=180)
        values = []
        for snap in snapshots:
            hormones = snap.get("hormones", {})
            value = hormones.get(hormone_key)
            if value is not None:
                values.append(float(value))
        if not values:
            await interaction.followup.send("No hormone history available yet.", ephemeral=True)
            return
        line = _sparkline(values)
        msg = f"{hormone_key} last {hours}h:\n`{line}`"
        await interaction.followup.send(msg[:2000], ephemeral=True)

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

    async def _cmd_confidence(self, interaction: discord.Interaction) -> None:
        """Show response confidence statistics."""
        await interaction.response.defer(ephemeral=True)
        scores = await self.state_manager.list_confidence_scores(limit=200)
        if scores:
            stats = self.confidence_scorer.summarize_scores(scores)
            source_label = "overall"
        else:
            stats = self.confidence_scorer.get_statistics()
            source_label = "session"

        from .confidence import get_confidence_emoji

        lines = ["**Response Confidence Statistics**\n"]
        lines.append(f"Total responses analyzed: {stats['total_responses']:,}")
        lines.append(f"Average confidence: {get_confidence_emoji(int(stats['average_confidence']))} {stats['average_confidence']}%")
        lines.append(f"Trend: {stats['confidence_trend']} ({source_label})")

        if stats.get('recent_scores'):
            lines.append("\n**Recent scores:**")
            for i, score in enumerate(stats['recent_scores'], 1):
                emoji = get_confidence_emoji(score)
                lines.append(f"{i}. {emoji} {score}%")

        msg = "\n".join(lines)
        await interaction.followup.send(msg[:2000], ephemeral=True)

    async def _cmd_bulk_delete(
        self,
        interaction: discord.Interaction,
        user_id: str,
        limit: int = 100
    ) -> None:
        """Bulk delete messages from a specific user in the current channel."""
        await interaction.response.defer(ephemeral=True)

        # Authorization check
        if not _is_authorized(interaction.user.id, self.settings.approval_user_id):
            await interaction.followup.send(
                "You are not authorized to use this command.",
                ephemeral=True
            )
            return

        try:
            # Validate user ID
            try:
                target_user_id = int(user_id)
            except ValueError:
                await interaction.followup.send(
                    f"Invalid user ID: {user_id}",
                    ephemeral=True
                )
                return

            # Get the channel
            channel = interaction.channel
            if not isinstance(channel, discord.TextChannel):
                await interaction.followup.send(
                    "This command can only be used in text channels.",
                    ephemeral=True
                )
                return

            # Fetch and delete messages
            deleted_count = 0
            async for message in channel.history(limit=limit):
                if message.author.id == target_user_id:
                    try:
                        await message.delete()
                        deleted_count += 1
                        # Add a small delay to avoid rate limiting
                        await asyncio.sleep(0.5)
                    except discord.errors.Forbidden:
                        logger.warning(f"Missing permissions to delete message {message.id}")
                    except discord.errors.NotFound:
                        logger.warning(f"Message {message.id} not found")
                    except Exception as e:
                        logger.error(f"Error deleting message {message.id}: {e}")

            await interaction.followup.send(
                f"Deleted {deleted_count} messages from user ID {user_id}",
                ephemeral=True
            )
            logger.info(
                f"Bulk delete: {interaction.user.name} deleted {deleted_count} messages "
                f"from user {user_id} in channel {channel.id}"
            )

        except Exception as e:
            await interaction.followup.send(
                f"Error during bulk delete: {str(e)}",
                ephemeral=True
            )
            logger.error(f"Bulk delete error: {e}")

    async def _cmd_purge_user_data(
        self,
        interaction: discord.Interaction,
        user_id: str
    ) -> None:
        """Remove all memories and data for a specific user from SEL's database."""
        await interaction.response.defer(ephemeral=True)

        # Authorization check
        if not _is_authorized(interaction.user.id, self.settings.approval_user_id):
            await interaction.followup.send(
                "You are not authorized to use this command.",
                ephemeral=True
            )
            return

        try:
            # Validate user ID
            try:
                target_user_id = str(int(user_id))  # Validate it's a number, then convert to string
            except ValueError:
                await interaction.followup.send(
                    f"Invalid user ID: {user_id}",
                    ephemeral=True
                )
                return

            from sqlalchemy import delete
            from .models import UserState, FeedbackEvent

            # Delete user state
            async with self.state_manager.session_factory() as session:
                result = await session.execute(
                    delete(UserState).where(UserState.user_id == target_user_id)
                )
                user_state_count = result.rowcount

                # Delete feedback events
                result = await session.execute(
                    delete(FeedbackEvent).where(FeedbackEvent.user_id == target_user_id)
                )
                feedback_count = result.rowcount

                await session.commit()

                total_removed = user_state_count + feedback_count
                await interaction.followup.send(
                    f"Purged data for user ID {user_id}:\n"
                    f"- {user_state_count} user state entries\n"
                    f"- {feedback_count} feedback events\n"
                    f"Total: {total_removed} entries removed",
                    ephemeral=True
                )
                logger.info(
                    f"Data purge: {interaction.user.name} removed {total_removed} entries "
                    f"for user {user_id}"
                )

        except Exception as e:
            await interaction.followup.send(
                f"Error during data purge: {str(e)}",
                ephemeral=True
            )
            logger.error(f"Data purge error: {e}")

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
            confidence_score=None,
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
