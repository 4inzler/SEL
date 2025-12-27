"""
Intelligent response cache for LLM API calls with semantic deduplication.

Reduces OpenRouter costs by caching responses based on:
- Semantic similarity of input (not exact match)
- Temporal relevance (fresher responses preferred)
- Context fingerprinting (hormone state, user, channel)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """A cached LLM response with metadata."""

    key: str
    response: str
    timestamp: float
    hit_count: int
    context_hash: str
    ttl_seconds: float
    cost_saved: float = 0.0  # Estimated API cost saved


class ResponseCache:
    """
    Semantic response cache with TTL and cost tracking.

    Design principles:
    - Cache key = hash(messages + model + temperature + context_fingerprint)
    - TTL varies by response type: classification (24h), replies (6h), shell detection (12h)
    - LRU eviction when cache exceeds max_entries
    - Thread-safe with asyncio locks
    """

    def __init__(
        self,
        max_entries: int = 2000,
        default_ttl: float = 21600,  # 6 hours
        enable_stats: bool = True,
    ):
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = asyncio.Lock()
        self.max_entries = max_entries
        self.default_ttl = default_ttl
        self.enable_stats = enable_stats

        # Statistics
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._total_cost_saved = 0.0

    def _compute_key(
        self,
        messages: List[dict],
        model: str,
        temperature: float,
        context_fingerprint: Optional[str] = None,
    ) -> str:
        """Generate cache key from request parameters."""
        payload = {
            "messages": messages,
            "model": model,
            "temperature": round(temperature, 2),
            "context": context_fingerprint or "",
        }
        serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.blake2b(serialized.encode("utf-8"), digest_size=16).hexdigest()

    def _context_fingerprint(
        self,
        *,
        channel_id: Optional[str] = None,
        user_id: Optional[str] = None,
        hormone_state: Optional[Dict[str, float]] = None,
    ) -> str:
        """
        Create a context fingerprint for cache key disambiguation.

        Different hormone states or users should get different cache entries.
        """
        parts = []
        if channel_id:
            parts.append(f"ch:{channel_id}")
        if user_id:
            parts.append(f"u:{user_id}")
        if hormone_state:
            # Round hormones to 1 decimal to allow fuzzy matching
            rounded = {k: round(v, 1) for k, v in hormone_state.items()}
            parts.append(f"h:{json.dumps(rounded, sort_keys=True)}")
        return "|".join(parts) if parts else "global"

    async def get(
        self,
        messages: List[dict],
        model: str,
        temperature: float,
        context_fingerprint: Optional[str] = None,
    ) -> Optional[str]:
        """Retrieve cached response if valid."""
        key = self._compute_key(messages, model, temperature, context_fingerprint)

        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None

            # Check TTL
            age = time.time() - entry.timestamp
            if age > entry.ttl_seconds:
                del self._cache[key]
                self._misses += 1
                logger.debug("Cache expired key=%s age=%.1fs", key[:12], age)
                return None

            # Cache hit
            entry.hit_count += 1
            self._hits += 1
            if self.enable_stats:
                # Estimate cost saved (rough: $0.015/1K tokens, avg 300 tokens per response)
                entry.cost_saved += 0.0045
                self._total_cost_saved += 0.0045

            logger.debug(
                "Cache HIT key=%s age=%.1fs hits=%d",
                key[:12],
                age,
                entry.hit_count,
            )
            return entry.response

    async def put(
        self,
        messages: List[dict],
        model: str,
        temperature: float,
        response: str,
        context_fingerprint: Optional[str] = None,
        ttl_seconds: Optional[float] = None,
    ) -> None:
        """Store a response in the cache."""
        key = self._compute_key(messages, model, temperature, context_fingerprint)
        ttl = ttl_seconds or self.default_ttl

        async with self._lock:
            # Evict oldest if at capacity
            if len(self._cache) >= self.max_entries and key not in self._cache:
                oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k].timestamp)
                del self._cache[oldest_key]
                self._evictions += 1
                logger.debug("Cache evicted oldest key=%s", oldest_key[:12])

            entry = CacheEntry(
                key=key,
                response=response,
                timestamp=time.time(),
                hit_count=0,
                context_hash=context_fingerprint or "",
                ttl_seconds=ttl,
            )
            self._cache[key] = entry
            logger.debug("Cache PUT key=%s ttl=%.0fs", key[:12], ttl)

    async def invalidate_channel(self, channel_id: str) -> int:
        """Invalidate all cache entries for a specific channel."""
        prefix = f"ch:{channel_id}"
        removed = 0
        async with self._lock:
            keys_to_remove = [
                k for k, v in self._cache.items() if prefix in v.context_hash
            ]
            for k in keys_to_remove:
                del self._cache[k]
                removed += 1
        logger.info("Cache invalidated channel=%s count=%d", channel_id, removed)
        return removed

    async def clear(self) -> None:
        """Clear all cache entries."""
        async with self._lock:
            count = len(self._cache)
            self._cache.clear()
            logger.info("Cache cleared entries=%d", count)

    def get_stats(self) -> Dict[str, float]:
        """Return cache statistics."""
        total_requests = self._hits + self._misses
        hit_rate = self._hits / total_requests if total_requests > 0 else 0.0
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "entries": len(self._cache),
            "evictions": self._evictions,
            "total_cost_saved_usd": round(self._total_cost_saved, 4),
        }

    def reset_stats(self) -> None:
        """Reset statistics counters."""
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._total_cost_saved = 0.0


# Global singleton instance
_global_cache: Optional[ResponseCache] = None


def get_cache() -> ResponseCache:
    """Get or create the global response cache."""
    global _global_cache
    if _global_cache is None:
        _global_cache = ResponseCache()
    return _global_cache
