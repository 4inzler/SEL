"""
Agent execution cache and performance monitoring.

Provides intelligent caching for deterministic agent operations and tracks
performance metrics for continuous improvement.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentExecutionMetrics:
    """Performance metrics for a single agent execution."""

    agent_name: str
    input_hash: str
    execution_time_ms: float
    success: bool
    error: Optional[str] = None
    cached: bool = False
    timestamp: float = field(default_factory=time.time)


@dataclass
class AgentCacheEntry:
    """Cached agent result with metadata."""

    result: str
    timestamp: float
    hit_count: int
    input_hash: str
    ttl_seconds: float


class AgentCache:
    """
    Intelligent agent execution cache with performance tracking.

    Design principles:
    - Cache deterministic agent results (e.g., fastfetch, system info)
    - Short TTL for dynamic data (1-5 minutes)
    - Track hit rates and execution times per agent
    - Thread-safe with asyncio locks
    """

    def __init__(
        self,
        max_entries: int = 500,
        default_ttl: float = 300,  # 5 minutes
        enable_metrics: bool = True,
    ):
        self._cache: Dict[str, AgentCacheEntry] = {}
        self._lock = asyncio.Lock()
        self.max_entries = max_entries
        self.default_ttl = default_ttl
        self.enable_metrics = enable_metrics

        # Performance metrics
        self._metrics: list[AgentExecutionMetrics] = []
        self._agent_stats: Dict[str, Dict] = {}  # name -> {calls, errors, avg_time_ms}

    def _compute_cache_key(self, agent_name: str, input_data: str) -> str:
        """Generate cache key from agent name and input."""
        payload = f"{agent_name}:{input_data}"
        return hashlib.blake2b(payload.encode("utf-8"), digest_size=12).hexdigest()

    async def get(
        self,
        agent_name: str,
        input_data: str,
        ttl_seconds: Optional[float] = None,
    ) -> Optional[str]:
        """Retrieve cached agent result if valid."""
        cache_key = self._compute_cache_key(agent_name, input_data)

        async with self._lock:
            entry = self._cache.get(cache_key)
            if entry is None:
                return None

            # Check TTL
            age = time.time() - entry.timestamp
            effective_ttl = ttl_seconds or entry.ttl_seconds
            if age > effective_ttl:
                del self._cache[cache_key]
                logger.debug(
                    "Agent cache expired agent=%s key=%s age=%.1fs",
                    agent_name,
                    cache_key[:8],
                    age,
                )
                return None

            # Cache hit
            entry.hit_count += 1
            logger.debug(
                "Agent cache HIT agent=%s key=%s age=%.1fs hits=%d",
                agent_name,
                cache_key[:8],
                age,
                entry.hit_count,
            )
            return entry.result

    async def put(
        self,
        agent_name: str,
        input_data: str,
        result: str,
        ttl_seconds: Optional[float] = None,
    ) -> None:
        """Store agent result in cache."""
        cache_key = self._compute_cache_key(agent_name, input_data)
        ttl = ttl_seconds or self.default_ttl

        async with self._lock:
            # Evict oldest if at capacity
            if len(self._cache) >= self.max_entries and cache_key not in self._cache:
                oldest_key = min(
                    self._cache.keys(), key=lambda k: self._cache[k].timestamp
                )
                del self._cache[oldest_key]
                logger.debug("Agent cache evicted key=%s", oldest_key[:8])

            entry = AgentCacheEntry(
                result=result,
                timestamp=time.time(),
                hit_count=0,
                input_hash=cache_key,
                ttl_seconds=ttl,
            )
            self._cache[cache_key] = entry
            logger.debug(
                "Agent cache PUT agent=%s key=%s ttl=%.0fs",
                agent_name,
                cache_key[:8],
                ttl,
            )

    async def log_execution(
        self,
        agent_name: str,
        input_data: str,
        execution_time_ms: float,
        success: bool,
        error: Optional[str] = None,
        cached: bool = False,
    ) -> None:
        """Record agent execution metrics."""
        if not self.enable_metrics:
            return

        input_hash = self._compute_cache_key(agent_name, input_data)
        metric = AgentExecutionMetrics(
            agent_name=agent_name,
            input_hash=input_hash,
            execution_time_ms=execution_time_ms,
            success=success,
            error=error,
            cached=cached,
        )

        async with self._lock:
            self._metrics.append(metric)
            # Keep only last 1000 metrics to avoid memory bloat
            if len(self._metrics) > 1000:
                self._metrics = self._metrics[-1000:]

            # Update agent-level stats
            if agent_name not in self._agent_stats:
                self._agent_stats[agent_name] = {
                    "total_calls": 0,
                    "cached_calls": 0,
                    "errors": 0,
                    "total_time_ms": 0.0,
                }

            stats = self._agent_stats[agent_name]
            stats["total_calls"] += 1
            if cached:
                stats["cached_calls"] += 1
            if not success:
                stats["errors"] += 1
            stats["total_time_ms"] += execution_time_ms

    def get_agent_stats(self, agent_name: Optional[str] = None) -> Dict:
        """Get performance statistics for agent(s)."""
        if agent_name:
            stats = self._agent_stats.get(agent_name, {})
            if stats:
                total_calls = stats["total_calls"]
                avg_time = (
                    stats["total_time_ms"] / total_calls if total_calls > 0 else 0
                )
                cache_rate = (
                    stats["cached_calls"] / total_calls if total_calls > 0 else 0
                )
                error_rate = stats["errors"] / total_calls if total_calls > 0 else 0
                return {
                    "agent": agent_name,
                    "total_calls": total_calls,
                    "cached_calls": stats["cached_calls"],
                    "cache_hit_rate": cache_rate,
                    "errors": stats["errors"],
                    "error_rate": error_rate,
                    "avg_execution_time_ms": avg_time,
                }
            return {}

        # All agents summary
        return {
            agent: self.get_agent_stats(agent) for agent in self._agent_stats.keys()
        }

    async def clear_agent(self, agent_name: str) -> int:
        """Clear all cache entries for a specific agent."""
        removed = 0
        async with self._lock:
            keys_to_remove = [
                k
                for k, v in self._cache.items()
                if k.startswith(self._compute_cache_key(agent_name, "")[:8])
            ]
            for k in keys_to_remove:
                del self._cache[k]
                removed += 1
        logger.info("Agent cache cleared agent=%s count=%d", agent_name, removed)
        return removed


# Global singleton
_global_agent_cache: Optional[AgentCache] = None


def get_agent_cache() -> AgentCache:
    """Get or create the global agent cache."""
    global _global_agent_cache
    if _global_agent_cache is None:
        _global_agent_cache = AgentCache()
    return _global_agent_cache
