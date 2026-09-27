import json

import pytest

from app.providers.triage.base import Category, Priority, TriageResult
from app.providers.triage.gemini import GeminiTriage
from app.providers.triage.rules import RuleBasedTriage
from app.redis_services import ComplaintRateLimiter, TriageCache
from app.schemas import ComplaintCreate
from app.services import ComplaintService


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.counts = {}
        self.expirations = {}

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, ex):
        self.values[key] = value
        self.expirations[key] = ex

    async def incr(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key, seconds):
        self.expirations[key] = seconds


class FakeRepository:
    async def create(self, complaint):
        return complaint


class FailingProvider:
    name = "simulated"

    async def triage(self, text, location):
        raise RuntimeError("provider unavailable")


@pytest.mark.asyncio
async def test_triage_cache_round_trip():
    cache = TriageCache(FakeRedis(), ttl_seconds=86400)
    result = TriageResult(category=Category.WATER, priority=Priority.HIGH, summary="Pipe burst", confidence=0.9)
    await cache.set("pipe burst", "Street 1", result)
    assert await cache.get("pipe burst", "Street 1") == result
    assert await cache.get("different", "Street 1") is None


@pytest.mark.asyncio
async def test_rate_limiter_rejects_after_limit():
    limiter = ComplaintRateLimiter(FakeRedis(), limit=2, window_seconds=60)
    assert (await limiter.check("127.0.0.1")).allowed
    assert (await limiter.check("127.0.0.1")).allowed
    rejected = await limiter.check("127.0.0.1")
    assert not rejected.allowed
    assert rejected.retry_after > 0


@pytest.mark.asyncio
async def test_provider_failure_returns_rules_fallback():
    service = ComplaintService(FakeRepository(), FailingProvider())
    complaint = await service.submit(ComplaintCreate(text="Burst water pipe flooding the road", location="Street 1"))
    assert complaint.triaged_by == "rules:fallback"
    assert complaint.category == Category.WATER
    assert complaint.priority == Priority.HIGH


def test_gemini_response_is_validated():
    payload = {
        "candidates": [{"content": {"parts": [{"text": json.dumps({
            "category": "roads",
            "priority": "normal",
            "summary": "Road damage near school",
            "confidence": 0.8,
        })}]}}]
    }
    result = GeminiTriage._parse_response(payload)
    assert result.category == Category.ROADS
    assert result.summary == "Road damage near school"


def test_gemini_malformed_response_is_rejected():
    with pytest.raises((ValueError, TypeError)):
        GeminiTriage._parse_response({"candidates": [{"content": {"parts": [{"text": "not json"}]}}]})
