"""Ollama triage provider -- the zero-dependency offline path (PDF 2.5).

"A container in your Compose file running a 1B-parameter model. No key, no
network, no rate limit, no PII leaving your machine. Slower on CPU and
noticeably worse at classification, which is itself the lesson."

Shares the same engineering envelope as the hosted provider: JSON-mode
structured output validated against TriageResult, 10 s timeout, single
jittered retry, content-hash cache (24 h TTL) with hit-rate tracking.
"""

import asyncio
import logging
import random
from typing import Any

import httpx

from app.providers.cache import CacheProvider
from app.providers.triage.base import TriageResult
from app.providers.triage.llm import (
    FENCE_CLOSE,
    FENCE_OPEN,
    LLMResponseError,
    SYSTEM_PROMPT,
    cache_key_for,
)
from app.services_stats import record_cache_hit, record_cache_miss

logger = logging.getLogger(__name__)


class OllamaTriage:
    """Fully offline path: Ollama container in the Compose stack."""

    name = "llm:ollama"

    def __init__(
        self,
        model: str = "llama3.2:1b",
        base_url: str = "http://ollama:11434",
        timeout_seconds: float = 30.0,
        cache: CacheProvider | None = None,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.cache = cache

    async def triage(self, text: str, location: str) -> TriageResult:
        # Same 24 h content-hash cache contract as the hosted provider.
        if self.cache is not None:
            key = cache_key_for(text, location)
            cached_json = await self.cache.get(key)
            if cached_json:
                record_cache_hit()
                return TriageResult.model_validate_json(cached_json)
            record_cache_miss()

        payload = await self._post_with_retry(self._build_request(text, location))
        result = self._parse_payload(payload)

        if self.cache is not None:
            await self.cache.set(
                cache_key_for(text, location),
                result.model_dump_json(),
                expire_seconds=86400,
            )
        return result

    def _build_request(self, text: str, location: str) -> dict[str, Any]:
        # Ollama /api/chat supports OpenAI-style "format": "json" for
        # structured output; the shape is still validated by TriageResult.
        return {
            "model": self.model,
            "format": "json",
            "stream": False,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"{FENCE_OPEN}{text}{FENCE_CLOSE}\nLocation: {location}"
                    ),
                },
            ],
            "options": {"temperature": 0},
        }

    async def _post_with_retry(self, request: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(
                        f"{self.base_url}/api/chat", json=request
                    )
                response.raise_for_status()
                return response.json()
            except httpx.TimeoutException as error:
                last_error = error
                retryable = attempt == 0
            except httpx.HTTPStatusError as error:
                last_error = error
                retryable = attempt == 0 and error.response.status_code >= 500
            if not retryable:
                raise last_error  # type: ignore[misc]
            await asyncio.sleep(0.1 + random.random() * 0.2)
        raise last_error  # type: ignore[misc]

    def _parse_payload(self, payload: dict[str, Any]) -> TriageResult:
        try:
            raw_text = payload["message"]["content"]
        except (KeyError, TypeError) as error:
            raise LLMResponseError("Ollama response did not contain message.content") from error
        if not isinstance(raw_text, str):
            raise LLMResponseError("Ollama response content was not a string")
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()
        try:
            import json

            data = json.loads(cleaned)
        except ValueError as error:
            raise LLMResponseError("Ollama response was not valid JSON") from error
        return TriageResult.model_validate(data)
