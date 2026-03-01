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
from .media_utils import resolve_image_url as _resolve_image_url
from .response_cache import get_cache
from .performance_monitor import get_monitor
from .prompts import VISION_ANALYSIS_PROMPT
from .vision_analysis import VisionAnalysis, coerce_vision_analysis, render_vision_analysis

logger = logging.getLogger(__name__)
_ASSIST_GUARDRAIL_TERMS = {
    "medical",
    "legal",
    "finance",
    "financial",
    "security",
    "password",
    "token",
    "api key",
    "credential",
    "sudo",
    " rm ",
    "deploy",
    "migration",
    "production",
}


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

    def _assist_direct_threshold(self) -> float:
        raw = getattr(self.settings, "llm_dual_model_assist_direct_threshold", 0.9)
        try:
            return max(0.0, min(1.0, float(raw)))
        except Exception:
            return 0.9

    @staticmethod
    def _needs_main_guardrails(user_content: str) -> bool:
        lowered = f" {str(user_content or '').lower()} "
        return any(term in lowered for term in _ASSIST_GUARDRAIL_TERMS)

    async def _generate_assist_package(self, messages: List[dict], user_content: str) -> dict[str, object]:
        prompt = (
            "You are a fast draft model assisting a larger verifier model.\n"
            "Return JSON only with keys:\n"
            "{\"draft\": string, \"confidence\": number 0..1, \"needs_main_model\": boolean, \"reason\": string}\n"
            "Guidelines:\n"
            "- Produce a concise, directly useful draft reply.\n"
            "- Set needs_main_model=true for high-risk, uncertain, or complex tasks.\n"
            "- Set confidence high only if the draft is likely correct as-is."
        )
        assist_messages = list(messages) + [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_content},
        ]
        raw = await self._chat_completion(
            model=self.settings.localai_util_model,
            messages=assist_messages,
            temperature=min(0.35, float(self.settings.localai_util_temp)),
            context_fingerprint=None,
            ttl_seconds=0,
        )
        parsed = self._parse_json_response(raw)
        if isinstance(parsed, dict):
            draft = str(parsed.get("draft", "") or "").strip()
            confidence = max(0.0, min(1.0, self._coerce_float(parsed.get("confidence"), 0.0)))
            needs_main = self._coerce_bool(parsed.get("needs_main_model"), default=True)
            reason = str(parsed.get("reason", "") or "").strip()[:180]
            return {
                "draft": draft[:2400],
                "confidence": confidence,
                "needs_main_model": needs_main,
                "reason": reason,
            }
        fallback_draft = (raw or "").strip()
        return {
            "draft": fallback_draft[:2400],
            "confidence": 0.0,
            "needs_main_model": True,
            "reason": "non_json_assist",
        }

    async def _refine_assist_package(
        self,
        messages: List[dict],
        user_content: str,
        draft: str,
    ) -> dict[str, object]:
        prompt = (
            "You are the second fast-assist pass in a quad pipeline.\n"
            "Critique and refine the first draft for clarity, factuality, and directness.\n"
            "Return JSON only with keys:\n"
            "{\"draft\": string, \"confidence\": number 0..1, \"needs_main_model\": boolean, \"reason\": string}\n"
            "Set needs_main_model=true for uncertainty, risky content, or ambiguous requests."
        )
        assist_messages = list(messages) + [
            {"role": "system", "content": prompt},
            {"role": "assistant", "content": draft[:2200]},
            {"role": "user", "content": user_content},
        ]
        raw = await self._chat_completion(
            model=self.settings.localai_util_model,
            messages=assist_messages,
            temperature=min(0.28, float(self.settings.localai_util_temp)),
            context_fingerprint=None,
            ttl_seconds=0,
        )
        parsed = self._parse_json_response(raw)
        if isinstance(parsed, dict):
            refined = str(parsed.get("draft", "") or "").strip()
            confidence = max(0.0, min(1.0, self._coerce_float(parsed.get("confidence"), 0.0)))
            needs_main = self._coerce_bool(parsed.get("needs_main_model"), default=True)
            reason = str(parsed.get("reason", "") or "").strip()[:180]
            return {
                "draft": refined[:2400] or draft[:2400],
                "confidence": confidence,
                "needs_main_model": needs_main,
                "reason": reason,
            }
        refined_fallback = (raw or "").strip()
        return {
            "draft": (refined_fallback or draft)[:2400],
            "confidence": 0.0,
            "needs_main_model": True,
            "reason": "non_json_refine",
        }

    def _should_run_second_main_pass(
        self,
        *,
        user_content: str,
        guardrail_force_main: bool,
        assist_confidence: float,
        first_reply: str,
    ) -> bool:
        if not bool(getattr(self.settings, "llm_quad_mode_enabled", True)):
            return False
        min_chars_raw = getattr(self.settings, "llm_quad_second_pass_min_chars", 220)
        try:
            min_chars = max(80, int(min_chars_raw))
        except Exception:
            min_chars = 220
        content = str(user_content or "")
        has_code = "```" in content
        complex_input = len(content) >= min_chars or has_code
        low_assist_confidence = assist_confidence < 0.55
        first_short = len((first_reply or "").strip()) < 18
        return guardrail_force_main or complex_input or low_assist_confidence or first_short

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

    def _build_vision_prompt(self, focus: Optional[str] = None) -> str:
        if focus:
            focus_clean = focus.strip()
            if focus_clean:
                return f"{VISION_ANALYSIS_PROMPT}\n\nFocus: {focus_clean}"
        return VISION_ANALYSIS_PROMPT

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

    async def analyze_image(self, image_url: str, prompt: Optional[str] = None) -> VisionAnalysis:
        """
        Analyze an image and return a structured vision analysis.
        """
        vision_prompt = self._build_vision_prompt(prompt)
        resolved_url = _resolve_image_url(image_url)
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": vision_prompt},
                    {"type": "image_url", "image_url": {"url": resolved_url}},
                ],
            }
        ]
        raw = await self._chat_completion(
            model=self.settings.localai_vision_model,
            messages=messages,
            temperature=0.2,
        )
        parsed = self._parse_json_response(raw)
        if not isinstance(parsed, dict):
            summary = (raw or "").strip()
            return VisionAnalysis(summary=summary)
        return coerce_vision_analysis(parsed)

    async def describe_image(self, image_url: str, prompt: str = "Describe this image.") -> str:
        """
        Use the vision-capable model to caption an image via its URL.
        Note: Requires LocalAI to be configured with a vision model like llava.
        """
        try:
            analysis = await self.analyze_image(image_url, prompt=prompt)
            rendered = render_vision_analysis(analysis)
            if rendered:
                return rendered
            return analysis.summary
        except Exception as exc:
            logger.warning("Structured vision analysis failed: %s", exc)

        resolved_url = _resolve_image_url(image_url)
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": resolved_url}},
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

        resolved_url = _resolve_image_url(image_url)
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": resolved_url}},
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
            "- Respond when someone is clearly talking to you\n"
            "- Stay quiet when people are talking to each other and not to you\n"
            "- Do not insert yourself into another person's conversation\n"
            "- If uncertain, choose silence\n"
            "- Continuations matter, but only if the thread clearly involves you\n\n"
            f"Your current mood: {mood_summary}\n"
            f"Is this a continuation of your conversation: {is_continuation}\n\n"
            "Respond with ONLY 'yes' or 'no'.\n"
            "Default to 'no'. Only say 'yes' when engagement is clearly appropriate."
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
            if "yes" in response and "no" not in response:
                return True
            if "no" in response and "yes" not in response:
                return False
            return bool(is_continuation)
        except Exception as e:
            logger.warning(f"Failed to get engagement decision: {e}")
            return bool(is_continuation)

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
        """Call reply pipeline (quad assist if enabled) and return final user-facing response."""
        base_temperature = temperature if temperature is not None else self.settings.localai_main_temp
        compiled = list(messages) + [{"role": "user", "content": user_content}]
        if not bool(getattr(self.settings, "llm_dual_model_assist_enabled", True)):
            return await self._chat_completion(
                model=self.settings.localai_main_model,
                messages=compiled,
                temperature=base_temperature,
                top_p=None,
            )

        assist: dict[str, object] = {}
        try:
            assist = await self._generate_assist_package(messages, user_content)
        except Exception as exc:
            logger.debug("Assist draft failed, falling back to main model: %s", exc)

        draft = str(assist.get("draft", "") or "").strip()
        confidence = self._coerce_float(assist.get("confidence"), 0.0)
        needs_main = self._coerce_bool(assist.get("needs_main_model"), default=True)

        if draft and bool(getattr(self.settings, "llm_quad_mode_enabled", True)):
            try:
                refined = await self._refine_assist_package(messages, user_content, draft)
                refined_draft = str(refined.get("draft", "") or "").strip()
                if refined_draft:
                    draft = refined_draft
                confidence = max(confidence, self._coerce_float(refined.get("confidence"), 0.0))
                needs_main = needs_main or self._coerce_bool(refined.get("needs_main_model"), default=True)
            except Exception as exc:
                logger.debug("Assist refine failed, keeping first draft: %s", exc)

        guardrail_force_main = self._needs_main_guardrails(user_content)
        allow_direct = bool(getattr(self.settings, "llm_dual_model_assist_allow_direct", True))
        direct_threshold = self._assist_direct_threshold()

        if (
            draft
            and allow_direct
            and not needs_main
            and confidence >= direct_threshold
            and not guardrail_force_main
        ):
            logger.debug("Assist direct path used confidence=%.2f", confidence)
            return draft

        if draft:
            verify_prompt = (
                "A smaller draft model produced the assistant reply.\n"
                "Verify and refine it for correctness, safety, and style.\n"
                "If it is already correct, keep it nearly unchanged.\n"
                "Return only the final user-facing reply."
            )
            verify_messages = list(messages) + [
                {"role": "system", "content": verify_prompt},
                {"role": "assistant", "content": draft[:2200]},
                {"role": "user", "content": user_content},
            ]
            try:
                first_main = await self._chat_completion(
                    model=self.settings.localai_main_model,
                    messages=verify_messages,
                    temperature=max(0.1, float(base_temperature) * 0.82),
                    top_p=None,
                )
                if not self._should_run_second_main_pass(
                    user_content=user_content,
                    guardrail_force_main=guardrail_force_main,
                    assist_confidence=confidence,
                    first_reply=first_main,
                ):
                    return first_main

                second_prompt = (
                    "Final verification pass. Improve only if needed for correctness, clarity, or safety. "
                    "If the prior answer is already good, keep it nearly unchanged. Return final reply only."
                )
                second_messages = list(messages) + [
                    {"role": "system", "content": second_prompt},
                    {"role": "assistant", "content": first_main[:2200]},
                    {"role": "user", "content": user_content},
                ]
                return await self._chat_completion(
                    model=self.settings.localai_main_model,
                    messages=second_messages,
                    temperature=max(0.1, float(base_temperature) * 0.76),
                    top_p=None,
                )
            except Exception as exc:
                logger.warning("Verifier model failed, returning assist draft: %s", exc)
                return draft

        return await self._chat_completion(
            model=self.settings.localai_main_model,
            messages=compiled,
            temperature=base_temperature,
            top_p=None,
        )

    async def get_embedding(self, text: str) -> List[float]:
        """
        Generate a text embedding via the local /v1/embeddings endpoint.

        Works with Ollama (nomic-embed-text), LocalAI, and any server that
        exposes an OpenAI-compatible embeddings endpoint.

        The model is controlled by MEMORY_EMBEDDING_MODEL (default:
        nomic-embed-text for local use).
        """
        if not self.settings.memory_embedding_enabled:
            raise ValueError("Embedding disabled by MEMORY_EMBEDDING_ENABLED=false")
        url = f"{self.base_url}/v1/embeddings"
        payload = {
            "model": self.settings.memory_embedding_model,
            "input": text[:8000],
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=self._headers(), json=payload)
            response.raise_for_status()
            return response.json()["data"][0]["embedding"]
