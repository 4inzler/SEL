"""
Backfill episodic memories from historical Discord conversations.

This script walks channel history, finds messages authored by Sel, pairs them with the
user messages they replied to, and writes summaries into the HIM-backed memory store.

Usage:
    DISCORD_BOT_TOKEN=... BACKFILL_CHANNEL_IDS=123,456 poetry run python -m tools.backfill_memories

Env vars:
    DISCORD_BOT_TOKEN     Required. Bot token with message content intent.
    BACKFILL_CHANNEL_IDS  Comma-separated channel IDs to scan. Required.
    BACKFILL_LIMIT        Per-channel message limit (default: 2000).
    BACKFILL_HIM_ROOT     Override HIM storage dir (defaults to Settings.him_memory_dir).
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

import discord
from dotenv import load_dotenv

from sel_bot.memory import MemoryManager

logger = logging.getLogger("backfill_memories")


def _parse_channel_ids(raw: Optional[str]) -> list[int]:
    if not raw:
        return []
    ids: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            logger.warning("Skipping invalid channel id: %s", part)
    return ids


def _compact(text: str, limit: int = 240) -> str:
    text = (text or "").strip()
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text or "(no content)"


class BackfillClient(discord.Client):
    def __init__(
        self,
        memory_manager: MemoryManager,
        channel_ids: list[int] | None,
        message_limit: int | None,
        **kwargs,
    ):
        intents = kwargs.pop("intents", discord.Intents.default())
        intents.message_content = True
        intents.messages = True
        super().__init__(intents=intents, **kwargs)
        self.memory_manager = memory_manager
        self.channel_ids = channel_ids or []
        self.message_limit = message_limit

    async def on_ready(self) -> None:
        assert self.user is not None
        logger.info("Connected as %s", self.user)
        channel_ids = list(self.channel_ids)
        if not channel_ids:
            collected: set[int] = set()
            for guild in self.guilds:
                for ch in guild.text_channels:
                    collected.add(ch.id)
                for th in guild.threads:
                    collected.add(th.id)
            channel_ids = sorted(collected)
            logger.info("Discovered %d channels to backfill", len(channel_ids))

        for channel_id in channel_ids:
            try:
                await self._backfill_channel(channel_id)
            except discord.Forbidden:
                logger.warning("Skipping channel %s due to missing access", channel_id)
            except Exception as exc:
                logger.warning("Skipping channel %s due to error: %s", channel_id, exc)
        await self.close()

    async def _backfill_channel(self, channel_id: int) -> None:
        try:
            channel = self.get_channel(channel_id) or await self.fetch_channel(channel_id)
        except Exception as exc:
            logger.warning("Unable to fetch channel %s: %s", channel_id, exc)
            return
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            logger.info("Skipping non-text channel %s", channel_id)
            return

        bot_id = self.user.id if self.user else None
        stored = 0
        last_user_msg: Optional[discord.Message] = None
        seen_summaries: set[str] = set()
        seen_bot_messages: set[int] = set()
        seen_user_messages: set[int] = set()

        try:
            history_limit = self.message_limit if self.message_limit and self.message_limit > 0 else None
            async for msg in channel.history(limit=history_limit, oldest_first=True):
                if bot_id and msg.author.id == bot_id:
                    if msg.id in seen_bot_messages:
                        continue
                    seen_bot_messages.add(msg.id)
                    paired: Optional[discord.Message] = None
                    if msg.reference:
                        paired = msg.reference.resolved or getattr(msg.reference, "cached_message", None)
                        if paired is None and msg.reference.message_id:
                            try:
                                paired = await channel.fetch_message(msg.reference.message_id)
                            except Exception:
                                paired = None
                    if paired and (not hasattr(paired, "author") or paired.author is None):
                        paired = None
                    if paired is None:
                        paired = last_user_msg

                    user_snippet = ""
                    if paired:
                        user_snippet = _compact(paired.content or "")
                        if not user_snippet and paired.attachments:
                            user_snippet = f"{len(paired.attachments)} attachment(s)"
                    sel_snippet = _compact(msg.content or "")
                    if not sel_snippet and msg.attachments:
                        sel_snippet = f"{len(msg.attachments)} attachment(s)"

                    summary = f"User:{' '+paired.author.display_name if paired else ''} {user_snippet}\nSel: {sel_snippet}"
                    if not user_snippet.strip() and not sel_snippet.strip():
                        continue
                    if summary in seen_summaries:
                        continue
                    try:
                        await self.memory_manager.maybe_store(
                            channel_id=str(channel.id),
                            summary=summary,
                            tags=["backfill", "history"],
                            salience=0.6,
                        )
                        seen_summaries.add(summary)
                        stored += 1
                    except Exception as exc:
                        logger.warning("Failed to store memory for channel=%s msg=%s: %s", channel.id, msg.id, exc)
                else:
                    if msg.id in seen_user_messages:
                        continue
                    seen_user_messages.add(msg.id)
                    # Store user messages directly addressed to Sel (mentions or replies)
                    addressed = False
                    if self.user and (self.user in msg.mentions):
                        addressed = True
                    if msg.reference and self.user:
                        ref = msg.reference.resolved or getattr(msg.reference, "cached_message", None)
                        if ref is None and msg.reference.message_id:
                            try:
                                ref = await channel.fetch_message(msg.reference.message_id)
                            except Exception:
                                ref = None
                        if ref and hasattr(ref, "author") and ref.author and ref.author.id == self.user.id:
                            addressed = True
                    if addressed:
                        user_snippet = _compact(msg.content or "")
                        if not user_snippet and msg.attachments:
                            user_snippet = f"{len(msg.attachments)} attachment(s)"
                        if user_snippet and user_snippet not in seen_summaries:
                            try:
                                await self.memory_manager.maybe_store(
                                    channel_id=str(channel.id),
                                    summary=f"User->{msg.author.display_name}: {user_snippet}",
                                    tags=["backfill", "user_message"],
                                    salience=0.5,
                                )
                                seen_summaries.add(user_snippet)
                                stored += 1
                            except Exception as exc:
                                logger.warning("Failed to store addressed message for channel=%s msg=%s: %s", channel.id, msg.id, exc)
                    last_user_msg = msg
        except discord.Forbidden:
            logger.warning("Missing access to read history for channel %s", channel.id)
            return
        except Exception as exc:
            logger.warning("Failed to read history for channel %s: %s", channel.id, exc)
            return

        logger.info("Channel %s backfill complete; stored %s memories", channel.id, stored)


async def main() -> None:
    load_dotenv()
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        raise SystemExit("DISCORD_BOT_TOKEN is required (set it in your environment or .env)")

    channel_ids = _parse_channel_ids(os.getenv("BACKFILL_CHANNEL_IDS"))
    raw_limit = os.getenv("BACKFILL_LIMIT", "")
    limit = int(raw_limit) if raw_limit.strip() else None
    him_root = Path(os.getenv("BACKFILL_HIM_ROOT") or os.getenv("HIM_MEMORY_DIR") or "sel_data/him_store")
    him_levels = int(os.getenv("HIM_MEMORY_LEVELS", "3"))

    memory_manager = MemoryManager(
        state_manager=None,
        him_root=him_root,
        max_level=him_levels,
    )

    client = BackfillClient(memory_manager=memory_manager, channel_ids=channel_ids, message_limit=limit)
    try:
        await client.start(token)
    finally:
        await client.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    asyncio.run(main())
