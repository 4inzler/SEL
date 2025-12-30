"""
HTTP client for LocalAI with OpenAI-compatible API.

LocalAI provides a drop-in replacement for OpenAI API that runs locally,
allowing SEL to operate without any cloud API costs.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Dict, List, Optional

import httpx

from .config import Settings
from .response_cache import get_cache
from .performance_monitor import get_monitor

logger = logging.getLogger(__name__)


class LocalAIClient:
    """
    LocalAI client implementing the same interface as OpenRouterClient.

    LocalAI uses OpenAI-compatible API endpoints, making it easy to swap.
    """

    def __init__(self, settings: Settings, enable_cache: bool = True) -> None:
        self.settings = settings
        self.enable_cache = enable_cache
        self.cache = get_cache() if enable_cache else None
        self.base_url = settings.localai_base_url.rstrip('/')
        self.api_key = settings.localai_api_key

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _parse_json_response(self, raw: str) -> Optional[object]:
        if not raw:
            return None
        text = raw.strip()
        if not text:
            return None
        if text.startswith("```"):
            match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
            if match:
                text = match.group(1).strip()

        # Clean up common malformed JSON patterns from LLM responses
        text = re.sub(r'"\s*":\s*"', '": "', text)
        text = re.sub(r':\s*":\s*', ': "', text)
        text = re.sub(r'"\s*"([^"]+)"\s*"', r'"\1"', text)

        decoder = json.JSONDecoder()
        try:
            return decoder.decode(text)
        except json.JSONDecodeError:
            pass
        for idx, ch in enumerate(text):
            if ch in "{[":
                try:
                    parsed, _ = decoder.raw_decode(text[idx:])
                    return parsed
                except json.JSONDecodeError:
                    continue
        return None

    def _coerce_bool(self, value: object, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "yes", "1"}:
                return True
            if normalized in {"false", "no", "0"}:
                return False
        if isinstance(value, (int, float)):
            return bool(value)
        return default

    def _coerce_float(self, value: object, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _strip_thinking_tags(self, text: str) -> str:
        """Remove internal thinking/reasoning tags from model responses."""
        if not text:
            return text
        # Remove <thinking>...</thinking> tags and their contents
        text = re.sub(r'<thinking>.*?</thinking>', '', text, flags=re.DOTALL | re.IGNORECASE)
        # Remove any other common reasoning tags
        text = re.sub(r'<reasoning>.*?</reasoning>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<internal>.*?</internal>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<internal_thinking>.*?</internal_thinking>', '', text, flags=re.DOTALL | re.IGNORECASE)
        # Also remove any standalone internal_thinking tags
        text = re.sub(r'</?internal_thinking>', '', text, flags=re.IGNORECASE)
        return text.strip()

    async def _chat_completion(
        self,
        model: str,
        messages: List[dict],
        temperature: float,
        top_p: Optional[float] = None,
        context_fingerprint: Optional[str] = None,
        ttl_seconds: Optional[float] = None,
    ) -> str:
        monitor = get_monitor()

        async with monitor.measure("llm", "chat_completion", {"model": model, "temperature": temperature}):
            if not model:
                raise ValueError("model is required for LocalAI call")

            # Sanitize message contents to avoid empty payload issues
            safe_messages = []
            for msg in messages:
                role = msg.get("role")
                content = msg.get("content") or "(no content)"
                safe_messages.append({"role": role, "content": content})

            # Check cache first
            if self.cache:
                cached = await self.cache.get(
                    safe_messages, model, temperature, context_fingerprint
                )
                if cached:
                    logger.debug("Cache hit for model=%s temp=%.2f", model, temperature)
                    return cached

            payload = {
                "model": model,
                "messages": safe_messages,
                "temperature": float(temperature),
            }
            if top_p is not None:
                payload["top_p"] = float(top_p)

            url = f"{self.base_url}/v1/chat/completions"

            async with httpx.AsyncClient(timeout=60.0) as client:
                try:
                    response = await client.post(url, headers=self._headers(), json=payload)
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    body = exc.response.text
                    raise httpx.HTTPStatusError(
                        f"{exc}: body={body[:500]}",
                        request=exc.request,
                        response=exc.response,
                    ) from exc
                data = response.json()
                result = data["choices"][0]["message"]["content"]

                # Strip internal reasoning/thinking tags before returning
                result = self._strip_thinking_tags(result)

                # Store in cache
                if self.cache:
                    await self.cache.put(
                        safe_messages,
                        model,
                        temperature,
                        result,
                        context_fingerprint=context_fingerprint,
                        ttl_seconds=ttl_seconds,
                    )

                return result

    async def describe_image(self, image_url: str, prompt: str = "Describe this image.") -> str:
        """
        Use the vision-capable model to caption an image via its URL.
        Note: Requires LocalAI to be configured with a vision model like llava.
        """
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            }
        ]
        return await self._chat_completion(
            model=self.settings.localai_vision_model,
            messages=messages,
            temperature=self.settings.localai_util_temp,
        )

    async def extract_text_from_image(self, image_url: str) -> Optional[str]:
        """
        Extract any text visible in an image using OCR via vision model.
        Note: Requires LocalAI to be configured with a vision model like llava.

        Returns the extracted text, or None if no text is found.
        """

        prompt = (
            "Extract ALL text visible in this image. "
            "Transcribe it exactly as it appears, preserving formatting, line breaks, and punctuation. "
            "If there is no text in the image, respond with: NO_TEXT_FOUND"
        )

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            }
        ]

        try:
            result = await self._chat_completion(
                model=self.settings.localai_vision_model,
                messages=messages,
                temperature=0.1,  # Low temperature for accurate transcription
            )

            if not result or "NO_TEXT_FOUND" in result.upper():
                return None

            return result.strip()

        except Exception as e:
            logger.error(f"OCR extraction failed: {e}")
            return None

    async def classify_message(self, content: str) -> Dict:
        """
        Use the utility model to classify sentiment, intensity, playful vs serious, and memory flag.
        Cached for 24h since message classification is deterministic.
        """
        prompt = (
            "Classify the message with JSON keys sentiment (positive|negative|neutral), "
            "intensity (0..1 float), playful (true/false), memory_write (true/false). "
            "Respond with JSON only."
        )
        messages = [{"role": "system", "content": prompt}, {"role": "user", "content": content}]
        default = {"sentiment": "neutral", "intensity": 0.3, "playful": False, "memory_write": False}
        try:
            raw = await self._chat_completion(
                model=self.settings.localai_util_model,
                messages=messages,
                temperature=self.settings.localai_util_temp,
                context_fingerprint="classify_message",
                ttl_seconds=86400,  # 24 hours
            )
        except Exception as exc:
            logger.error("classify_message failed: %s", exc, exc_info=True)
            return default

        parsed = self._parse_json_response(raw)
        if not isinstance(parsed, dict):
            if not raw or not raw.strip():
                logger.debug("classify_message empty response; using default")
            else:
                logger.warning("classify_message invalid JSON: %r", raw[:200])
            return default

        sentiment = parsed.get("sentiment")
        if sentiment not in {"positive", "negative", "neutral"}:
            sentiment = default["sentiment"]
        intensity = self._coerce_float(parsed.get("intensity"), default["intensity"])
        intensity = max(0.0, min(1.0, intensity))
        playful = self._coerce_bool(parsed.get("playful"), default["playful"])
        memory_write = self._coerce_bool(parsed.get("memory_write"), default["memory_write"])
        return {
            "sentiment": sentiment,
            "intensity": intensity,
            "playful": playful,
            "memory_write": memory_write,
        }

    async def generate_self_improvement_suggestions(self, context: str) -> List[dict]:
        """Ask the utility model for safe, high-level improvement suggestions."""
        prompt = (
            "You are Sel's safety harness. Emit at most 3 concise suggestions to improve prompts, "
            "configuration, or tests. Return JSON list like [{\"category\":\"config\", "
            "\"title\":\"raise empathy slightly\", \"detail\":\"Set empathy +0.05 to soften tone\"}]. "
            "Never include secrets, tokens, or code that executes. Keep details under 320 chars."
        )
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": context[:1200]},
        ]
        try:
            raw = await self._chat_completion(
                model=self.settings.localai_util_model,
                messages=messages,
                temperature=self.settings.localai_util_temp,
            )
        except Exception:
            return []
        parsed = self._parse_json_response(raw)
        if isinstance(parsed, dict):
            parsed = parsed.get("suggestions", []) if isinstance(parsed.get("suggestions", []), list) else []
        return parsed if isinstance(parsed, list) else []

    async def classify_shell_command(self, content: str) -> Optional[Dict[str, object]]:
        """
        Detect if a message is asking about the system or needs shell access.
        Returns {"intent":bool,"command":str}. Command may be empty for natural language queries.
        """
        prompt = (
            "Decide if the user is asking about the system or needs shell/system access. "
            "Respond JSON: {\"intent\":true/false, \"command\":\"<bash snippet if explicit, or empty>\"}. "
            "Set intent=true for:\n"
            "- Explicit commands (run ls, tail logs, cat file, ps, top)\n"
            "- System queries (disk space, memory, what's running, port usage)\n"
            "- File/directory questions (what's in /tmp, show me the logs)\n"
            "- Service/process inquiries (is docker running, service status)\n"
            "- Navigation (where am i, go to /home)\n"
            "Set intent=false for general chat, coding questions, or non-system topics."
        )
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": content[:500]},
        ]
        try:
            raw = await self._chat_completion(
                model=self.settings.localai_util_model,
                messages=messages,
                temperature=self.settings.localai_util_temp,
                context_fingerprint="shell_command",
                ttl_seconds=43200,  # 12 hours
            )
        except Exception:
            return None
        data = self._parse_json_response(raw)
        if not isinstance(data, dict):
            return None
        intent = self._coerce_bool(data.get("intent"))
        command = str(data.get("command") or "").strip()
        return {"intent": intent, "command": command}

    async def should_engage_naturally(
        self,
        recent_conversation: str,
        user_message: str,
        mood_summary: str,
        is_continuation: bool
    ) -> bool:
        """Decide if SEL should naturally engage in this conversation."""
        prompt = (
            "You are Sel, a Discord bot with personality and emotions. Based on the conversation "
            "and your current mood, decide if you should respond.\n\n"
            "Respond like a human would:\n"
            "- Jump in if you have something relevant to say\n"
            "- Stay quiet if others are having a focused 1-on-1 conversation\n"
            "- Engage more when curious, energetic, or the topic interests you\n"
            "- Hold back when tired, stressed, or the conversation doesn't involve you\n"
            "- Sometimes chime in spontaneously if you have insights\n\n"
            f"Your current mood: {mood_summary}\n"
            f"Is this a continuation of your conversation: {is_continuation}\n\n"
            "Respond with ONLY 'yes' or 'no' - should you engage?"
        )

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Recent conversation:\n{recent_conversation}\n\nLatest message: {user_message}"}
        ]

        try:
            raw = await self._chat_completion(
                model=self.settings.localai_util_model,
                messages=messages,
                temperature=0.7,
                context_fingerprint=None,
                ttl_seconds=0,
            )
            response = raw.strip().lower()
            return "yes" in response
        except Exception as e:
            logger.warning(f"Failed to get engagement decision: {e}")
            return is_continuation

    async def generate_agent_ack(
        self, agent: str, action: str, result: str, *, style_hint: Optional[str] = None
    ) -> Optional[str]:
        """Ask the util model to craft a short, friendly acknowledgement for an agent action."""
        prompt = (
            "You are Sel. Write a brief, friendly one-sentence confirmation of an action just taken. "
            "Mention the action/command explicitly. Keep under 160 characters. Avoid brackets like [music]."
        )
        if style_hint:
            prompt += f" Style hint: {style_hint}"
        user = f"Agent '{agent}' executed action '{action}'. Result: {result[:500]}"
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user},
        ]
        try:
            return await self._chat_completion(
                model=self.settings.localai_util_model,
                messages=messages,
                temperature=self.settings.localai_util_temp,
            )
        except Exception:
            return None

    async def generate_reply(
        self,
        messages: List[dict],
        user_content: str,
        temperature: Optional[float] = None,
    ) -> str:
        """Call the main model with assembled system messages plus the user content."""
        compiled = list(messages) + [{"role": "user", "content": user_content}]
        return await self._chat_completion(
            model=self.settings.localai_main_model,
            messages=compiled,
            temperature=temperature if temperature is not None else self.settings.localai_main_temp,
            top_p=None,  # LocalAI doesn't always support top_p
        )
