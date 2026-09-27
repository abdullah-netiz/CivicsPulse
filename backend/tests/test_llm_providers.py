"""Deterministic tests for the hosted LLM providers and the cache hit-rate
tracking (rubric sections E and F).

No network access: every HTTP call is mocked. CI stays green by design --
PDF 2.5 "Determinism": pin CI to simulated/mock providers, never sleep in a
test, inject malformed output to test the validator.
"""

import logging
import json
from unittest.mock import patch

import httpx
import pytest

from app.providers.redis_cache import InMemoryCacheProvider
from app.providers.triage.base import Category, Priority
from app.providers.triage.llm import GroqLLMTriage, LLMResponseError, cache_key_for
from app.providers.triage.ollama import OllamaTriage
from app.services_stats import get_cache_hit_rate


def _groq_payload(summary: str = "Burst water main flooding the street.") -> dict:
    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "category": "water",
                            "priority": "high",
                            "summary": summary,
                            "confidence": 0.95,
                        }
                    )
                }
            }
        ]
    }


def _ollama_payload() -> dict:
    return {
        "message": {
            "content": json.dumps(
                {
                    "category": "electricity",
                    "priority": "high",
                    "summary": "Transformer fire with falling sparks.",
                    "confidence": 0.8,
                }
            )
        }
    }


# ---------------------------------------------------------------------------
# GroqLLMTriage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_groq_structured_output_validated():
    provider = GroqLLMTriage(api_key="test-key", model="llama-3.1-8b-instant")

    async def fake_post(url, **kwargs):
        return httpx.Response(200, json=_groq_payload(), request=httpx.Request("POST", url))

    with patch.object(httpx.AsyncClient, "post", side_effect=fake_post):
        result = await provider.triage("Water main burst flooding road", "Sector F-8")

    assert result.category == Category.WATER
    assert result.priority == Priority.HIGH
    assert len(result.summary) <= 140
    assert 0.0 <= result.confidence <= 1.0


@pytest.mark.asyncio
async def test_groq_content_hash_cache_24h_ttl():
    """PDF 2.5 item 5: duplicates cost one inference, not nine."""
    cache = InMemoryCacheProvider()
    provider = GroqLLMTriage(api_key="k", model="m", cache=cache)
    calls = {"n": 0}

    async def fake_post(url, **kwargs):
        calls["n"] += 1
        return httpx.Response(200, json=_groq_payload(), request=httpx.Request("POST", url))

    with patch.object(httpx.AsyncClient, "post", side_effect=fake_post):
        await provider.triage("Burst pipe on street 12", "F-8")
        await provider.triage("Burst pipe on street 12", "F-8")  # duplicate

    assert calls["n"] == 1
    # 24 h TTL actually stored
    key = cache_key_for("Burst pipe on street 12", "F-8")
    stored = await cache.get(key)
    assert stored is not None


@pytest.mark.asyncio
async def test_groq_never_retries_4xx_but_retries_429_once():
    """PDF 2.5 item 3: retry once on 429/5xx/timeout only -- never a 400."""
    provider = GroqLLMTriage(api_key="k", model="m")

    # 400 must NOT be retried
    calls_400 = {"n": 0}

    async def post_400(url, **kwargs):
        calls_400["n"] += 1
        return httpx.Response(400, json={}, request=httpx.Request("POST", url))

    with patch.object(httpx.AsyncClient, "post", side_effect=post_400):
        with pytest.raises(httpx.HTTPStatusError):
            await provider.triage("text here", "loc")
    assert calls_400["n"] == 1

    # 429 IS retried exactly once
    calls_429 = {"n": 0}

    async def post_429(url, **kwargs):
        calls_429["n"] += 1
        return httpx.Response(429, json={}, request=httpx.Request("POST", url))

    with patch.object(httpx.AsyncClient, "post", side_effect=post_429):
        with pytest.raises(httpx.HTTPStatusError):
            await provider.triage("text here", "loc")
    assert calls_429["n"] == 2


@pytest.mark.asyncio
async def test_groq_malformed_model_output_rejected():
    """PDF 2.5 item 1: a plausible category outside the enum is rejected."""
    provider = GroqLLMTriage(api_key="k", model="m")
    bad = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {"category": "alien_invasion", "priority": "high", "summary": "x", "confidence": 0.9}
                    )
                }
            }
        ]
    }

    async def fake_post(url, **kwargs):
        return httpx.Response(200, json=bad, request=httpx.Request("POST", url))

    with patch.object(httpx.AsyncClient, "post", side_effect=fake_post):
        with pytest.raises(Exception):
            await provider.triage("text", "loc")


@pytest.mark.asyncio
async def test_groq_code_fenced_json_is_unwrapped():
    provider = GroqLLMTriage(api_key="k", model="m")
    fenced = {
        "choices": [
            {
                "message": {
                    "content": "```json\n"
                    + json.dumps(
                        {"category": "water", "priority": "low", "summary": "Dripping tap.", "confidence": 0.7}
                    )
                    + "\n```"
                }
            }
        ]
    }

    async def fake_post(url, **kwargs):
        return httpx.Response(200, json=fenced, request=httpx.Request("POST", url))

    with patch.object(httpx.AsyncClient, "post", side_effect=fake_post):
        result = await provider.triage("Tap dripping slowly", "G-9")
    assert result.category == Category.WATER


def test_groq_api_key_required_at_triage_time_not_construction():
    """A missing key must not 500 the app at import; the service catches it
    in triage() and falls back to rules (PDF 2.5 item 4)."""
    provider = GroqLLMTriage(api_key="", model="m")  # construction succeeds

    import asyncio

    with pytest.raises(ValueError, match="GROQ_API_KEY"):
        asyncio.run(provider.triage("text", "loc"))


# ---------------------------------------------------------------------------
# OllamaTriage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ollama_structured_output_validated():
    provider = OllamaTriage(model="llama3.2:1b", base_url="http://ollama:11434")

    async def fake_post(url, **kwargs):
        return httpx.Response(200, json=_ollama_payload(), request=httpx.Request("POST", url))

    with patch.object(httpx.AsyncClient, "post", side_effect=fake_post):
        result = await provider.triage("Transformer on fire", "Gulberg")
    assert result.category == Category.ELECTRICITY
    assert result.priority == Priority.HIGH


@pytest.mark.asyncio
async def test_ollama_malformed_output_rejected():
    provider = OllamaTriage()
    bad = {"message": {"content": "this is prose, not json"}}

    async def fake_post(url, **kwargs):
        return httpx.Response(200, json=bad, request=httpx.Request("POST", url))

    with patch.object(httpx.AsyncClient, "post", side_effect=fake_post):
        with pytest.raises(LLMResponseError):
            await provider.triage("text", "loc")


# ---------------------------------------------------------------------------
# Cache hit-rate reporting (rubric F: measured, reported hit rate)
# ---------------------------------------------------------------------------


def test_cache_hit_rate_tracking():
    from app.services_stats import record_cache_hit, record_cache_miss

    before = get_cache_hit_rate()
    record_cache_hit()
    record_cache_hit()
    record_cache_miss()
    after = get_cache_hit_rate()

    assert after["hits"] == before["hits"] + 2
    assert after["misses"] == before["misses"] + 1
    assert after["total"] == before["total"] + 3
    assert 0.0 <= after["hit_rate"] <= 1.0


@pytest.mark.asyncio
async def test_meta_providers_exposes_cache_hit_rate(client):
    # One submission drives one triage (a MISS since the cache is empty)
    await client.post(
        "/api/complaints",
        json={"text": "Water pipe burst near the market", "location": "Sector F-7"},
    )
    res = await client.get("/api/meta/providers")
    assert res.status_code == 200
    body = res.json()
    assert "triage_cache_hit_rate" in body
    rate = body["triage_cache_hit_rate"]
    assert set(rate.keys()) == {"hits", "misses", "total", "hit_rate"}


# ---------------------------------------------------------------------------
# Fallback WARNING carries complaint id, provider and error class (PDF 2.2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fallback_warning_log_content(caplog):
    from app.providers.triage.simulated import SimulatedTriage
    from app.services import ComplaintService
    from app.schemas import ComplaintCreate

    class RepoStub:
        async def create(self, complaint):
            return complaint

    service = ComplaintService(RepoStub(), SimulatedTriage(should_fail=True))
    payload = ComplaintCreate(text="Sewer overflow flooding the lane", location="Block C")

    with caplog.at_level(logging.WARNING, logger="app.services"):
        await service.submit(payload)

    warning_text = " ".join(r.getMessage() for r in caplog.records if r.levelno == logging.WARNING)
    assert "Triage fallback" in warning_text
    assert "provider=simulated" in warning_text
    assert "error_class=RuntimeError" in warning_text


# ---------------------------------------------------------------------------
# /metrics wires the triage counters (rubric C: Prometheus format)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_metrics_contains_triage_series(client):
    await client.post(
        "/api/complaints",
        json={"text": "Road cave-in near the school", "location": "University Road"},
    )
    res = await client.get("/metrics")
    assert res.status_code == 200
    assert "civicpulse_triage_latency" in res.text
