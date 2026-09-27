import hashlib
import json
import time
from dataclasses import dataclass

from redis.asyncio import Redis

from app.providers.triage.base import TriageResult


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after: int


class TriageCache:
    def __init__(self, client: Redis, ttl_seconds: int = 86400):
        self.client = client
        self.ttl_seconds = ttl_seconds

    @staticmethod
    def key(text: str, location: str) -> str:
        digest = hashlib.sha256(f"{text}\n{location}".encode("utf-8")).hexdigest()
        return f"civicpulse:triage:{digest}"

    async def get(self, text: str, location: str) -> TriageResult | None:
        cached = await self.client.get(self.key(text, location))
        if cached is None:
            return None
        if isinstance(cached, bytes):
            cached = cached.decode("utf-8")
        return TriageResult.model_validate(json.loads(cached))

    async def set(self, text: str, location: str, result: TriageResult) -> None:
        await self.client.set(self.key(text, location), result.model_dump_json(), ex=self.ttl_seconds)


class ComplaintRateLimiter:
    def __init__(self, client: Redis, limit: int = 10, window_seconds: int = 60):
        self.client = client
        self.limit = limit
        self.window_seconds = window_seconds

    async def check(self, client_ip: str) -> RateLimitResult:
        window = int(time.time()) // self.window_seconds
        key = f"civicpulse:rate:{client_ip}:{window}"
        count = await self.client.incr(key)
        if count == 1:
            await self.client.expire(key, self.window_seconds)
        if count <= self.limit:
            return RateLimitResult(allowed=True, retry_after=0)
        retry_after = self.window_seconds - (int(time.time()) % self.window_seconds)
        return RateLimitResult(allowed=False, retry_after=max(1, retry_after))
