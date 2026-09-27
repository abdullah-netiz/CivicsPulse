"""Triage content-hash cache hit-rate tracking (PDF rubric F: measured,
reported hit rate).

PDF 2.5 item 5: "Cache by content hash in Redis, 24 h TTL ... Report your
measured hit rate."

Counters live in process memory and are exposed through
GET /api/meta/providers. They are deliberately not persisted: the hit rate
is an operational observation of the running process, not durable state.
"""

from threading import Lock

_lock = Lock()
_cache_hits = 0
_cache_misses = 0


def record_cache_hit() -> None:
    global _cache_hits
    with _lock:
        _cache_hits += 1


def record_cache_miss() -> None:
    global _cache_misses
    with _lock:
        _cache_misses += 1


def get_cache_hit_rate() -> dict:
    with _lock:
        total = _cache_hits + _cache_misses
        rate = (_cache_hits / total) if total > 0 else 0.0
        return {
            "hits": _cache_hits,
            "misses": _cache_misses,
            "total": total,
            "hit_rate": round(rate, 4),
        }
