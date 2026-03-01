"""
ElevenLabs API client for TTS and STT.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


def _unique(values: list) -> list:
    seen = set()
    ordered = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


class ElevenLabsClient:
    def __init__(self, api_key: str, base_url: str = "https://api.elevenlabs.io") -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {
            "xi-api-key": self._api_key,
        }

    async def synthesize(
        self,
        *,
        text: str,
        voice_id: str,
        model_id: str,
        output_format: str,
        language_code: str | None = None,
        voice_settings: dict | None = None,
        enable_logging: bool = True,
    ) -> bytes:
        output_candidates = _unique(
            [
                output_format or None,
                "mp3_44100_128",
                "mp3_44100_64",
                "mp3_22050_32",
                None,
            ]
        )
        model_candidates = _unique(
            [
                model_id or None,
                "eleven_multilingual_v2",
                "eleven_turbo_v2",
                "eleven_monolingual_v1",
                None,
            ]
        )
        log_400 = True
        last_exc: httpx.HTTPStatusError | None = None

        async with httpx.AsyncClient(base_url=self._base_url, timeout=30.0) as client:
            for model in model_candidates:
                for fmt in output_candidates:
                    params: dict[str, str] = {}
                    if fmt:
                        params["output_format"] = fmt
                    if not enable_logging:
                        params["enable_logging"] = "false"

                    payload: dict[str, object] = {"text": text}
                    if model:
                        payload["model_id"] = model
                    if language_code:
                        payload["language_code"] = language_code
                    if voice_settings:
                        payload["voice_settings"] = voice_settings

                    resp = await client.post(
                        f"/v1/text-to-speech/{voice_id}",
                        params=params,
                        headers={**self._headers(), "Content-Type": "application/json"},
                        json=payload,
                    )
                    try:
                        resp.raise_for_status()
                    except httpx.HTTPStatusError as exc:
                        if resp.status_code in (400, 422):
                            if log_400:
                                body = (resp.text or "").strip()
                                logger.warning(
                                    "ElevenLabs TTS rejected request (status=%s): %s",
                                    resp.status_code,
                                    body[:400],
                                )
                                log_400 = False
                            last_exc = exc
                            continue
                        raise
                    return resp.content
        if last_exc:
            raise last_exc
        raise httpx.HTTPError("ElevenLabs TTS failed with no response content.")

    async def transcribe(
        self,
        *,
        audio_bytes: bytes,
        filename: str,
        model_id: str,
        language_code: str | None = None,
        content_type: str | None = None,
        enable_logging: bool = True,
    ) -> dict:
        params: dict[str, str] = {}
        if not enable_logging:
            params["enable_logging"] = "false"

        data = {"model_id": model_id}
        if language_code:
            data["language_code"] = language_code

        files = {
            "file": (filename, audio_bytes, content_type or "application/octet-stream")
        }

        async with httpx.AsyncClient(base_url=self._base_url, timeout=60.0) as client:
            resp = await client.post(
                "/v1/speech-to-text",
                params=params,
                headers=self._headers(),
                data=data,
                files=files,
            )
            resp.raise_for_status()
            return resp.json()
