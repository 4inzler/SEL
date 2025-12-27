"""
Metrics and health check API endpoints for SEL bot monitoring.

Provides real-time performance metrics, cache statistics, and system health.
Can be mounted on the HIM API or run as a standalone service.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict

from fastapi import APIRouter, Response

from .agent_cache import get_agent_cache
from .hormone_analytics import create_analytics
from .performance_monitor import get_monitor
from .response_cache import get_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/metrics", tags=["monitoring"])


@router.get("/health")
async def health_check() -> Dict:
    """
    Simple health check endpoint.

    Returns:
        Status and basic system info
    """
    return {
        "status": "healthy",
        "service": "sel-bot",
        "version": "1.0.0",
    }


@router.get("/performance")
async def performance_metrics() -> Dict:
    """
    Get comprehensive performance statistics.

    Returns:
        Performance metrics for all subsystems (LLM, HIM, agents, hormones)
    """
    monitor = get_monitor()
    stats = await monitor.get_all_stats()
    return stats


@router.get("/performance/{subsystem}")
async def subsystem_performance(subsystem: str) -> Dict:
    """
    Get detailed performance stats for a specific subsystem.

    Args:
        subsystem: One of "llm", "him", "agent", "hormone", "discord"

    Returns:
        Detailed metrics for the subsystem
    """
    monitor = get_monitor()
    stats = await monitor.get_subsystem_stats(subsystem)
    return {
        "subsystem": stats.subsystem,
        "total_operations": stats.total_operations,
        "successful_operations": stats.successful_operations,
        "failed_operations": stats.failed_operations,
        "success_rate_pct": stats.success_rate,
        "avg_duration_ms": stats.avg_duration_ms,
        "min_duration_ms": stats.min_duration_ms,
        "max_duration_ms": stats.max_duration_ms,
        "p50_duration_ms": stats.p50_duration_ms,
        "p95_duration_ms": stats.p95_duration_ms,
        "p99_duration_ms": stats.p99_duration_ms,
    }


@router.get("/slow-operations")
async def slow_operations(threshold_ms: float = 1000.0) -> Dict:
    """
    Find operations exceeding a duration threshold.

    Args:
        threshold_ms: Minimum duration in milliseconds (default 1000ms)

    Returns:
        List of slow operations with details
    """
    monitor = get_monitor()
    slow_ops = await monitor.get_slow_operations(threshold_ms)
    return {
        "threshold_ms": threshold_ms,
        "count": len(slow_ops),
        "operations": slow_ops[:50],  # Limit to 50 slowest
    }


@router.get("/cache/llm")
async def llm_cache_stats() -> Dict:
    """
    Get LLM response cache statistics.

    Returns:
        Cache hit rate, entries, cost savings
    """
    cache = get_cache()
    stats = cache.get_stats()
    return {
        "type": "llm_response_cache",
        "hits": stats["hits"],
        "misses": stats["misses"],
        "hit_rate_pct": stats["hit_rate"] * 100.0,
        "entries": stats["entries"],
        "evictions": stats["evictions"],
        "total_cost_saved_usd": stats["total_cost_saved_usd"],
        "estimated_monthly_savings_usd": stats["total_cost_saved_usd"] * 30,  # Rough estimate
    }


@router.get("/cache/agent")
async def agent_cache_stats() -> Dict:
    """
    Get agent execution cache statistics.

    Returns:
        Per-agent cache performance and execution stats
    """
    cache = get_agent_cache()
    all_stats = cache.get_agent_stats()
    return {
        "type": "agent_execution_cache",
        "agents": all_stats,
    }


@router.get("/prometheus")
async def prometheus_metrics() -> Response:
    """
    Export metrics in Prometheus text format.

    Returns:
        Plain text metrics in Prometheus exposition format
    """
    monitor = get_monitor()
    metrics_text = await monitor.export_prometheus_metrics()

    # Add cache metrics
    llm_cache = get_cache()
    llm_stats = llm_cache.get_stats()

    additional_metrics = f"""
# HELP sel_llm_cache_hits_total LLM cache hits
# TYPE sel_llm_cache_hits_total counter
sel_llm_cache_hits_total {llm_stats["hits"]}

# HELP sel_llm_cache_misses_total LLM cache misses
# TYPE sel_llm_cache_misses_total counter
sel_llm_cache_misses_total {llm_stats["misses"]}

# HELP sel_llm_cache_hit_rate Cache hit rate
# TYPE sel_llm_cache_hit_rate gauge
sel_llm_cache_hit_rate {llm_stats["hit_rate"]}

# HELP sel_llm_cache_cost_saved_total Total cost saved in USD
# TYPE sel_llm_cache_cost_saved_total counter
sel_llm_cache_cost_saved_total {llm_stats["total_cost_saved_usd"]}
"""

    full_metrics = metrics_text + additional_metrics

    return Response(
        content=full_metrics,
        media_type="text/plain; version=0.0.4",
    )


@router.post("/cache/clear/llm")
async def clear_llm_cache() -> Dict:
    """
    Clear the LLM response cache.

    Returns:
        Confirmation with count of cleared entries
    """
    cache = get_cache()
    stats_before = cache.get_stats()
    await cache.clear()
    return {
        "status": "cleared",
        "entries_cleared": stats_before["entries"],
    }


@router.post("/cache/clear/agent/{agent_name}")
async def clear_agent_cache(agent_name: str) -> Dict:
    """
    Clear cache for a specific agent.

    Args:
        agent_name: Name of agent to clear

    Returns:
        Confirmation with count of cleared entries
    """
    cache = get_agent_cache()
    count = await cache.clear_agent(agent_name)
    return {
        "status": "cleared",
        "agent": agent_name,
        "entries_cleared": count,
    }


@router.get("/hormones/trends/{channel_id}")
async def hormone_trends(
    channel_id: str,
    hours: int = 24,
    level: int = 1,
) -> Dict:
    """
    Analyze hormone trends for a channel.

    Args:
        channel_id: Discord channel ID
        hours: Hours of history to analyze
        level: HIM pyramid level (0=5min, 1=hourly, 2=daily, 3=weekly)

    Returns:
        Detected hormone trends with confidence scores
    """
    import datetime as dt

    analytics = create_analytics()
    end_time = dt.datetime.now(dt.timezone.utc)
    start_time = end_time - dt.timedelta(hours=hours)

    trends = await analytics.analyze_trends(channel_id, start_time, end_time, level)

    return {
        "channel_id": channel_id,
        "analysis_period": {
            "start": start_time.isoformat(),
            "end": end_time.isoformat(),
            "hours": hours,
        },
        "trends": [
            {
                "hormone": t.hormone_name,
                "direction": t.direction,
                "slope_per_hour": t.slope,
                "confidence": t.confidence,
                "significance": t.significance,
                "start_value": t.start_value,
                "end_value": t.end_value,
                "change": t.end_value - t.start_value,
            }
            for t in trends
        ],
    }


@router.get("/hormones/anomalies/{channel_id}")
async def hormone_anomalies(
    channel_id: str,
    window_hours: int = 24,
    sensitivity: float = 2.0,
) -> Dict:
    """
    Detect hormone anomalies (spikes/drops).

    Args:
        channel_id: Discord channel ID
        window_hours: Hours of history to analyze
        sensitivity: Standard deviations for anomaly threshold

    Returns:
        Detected anomalies with severity scores
    """
    analytics = create_analytics()
    anomalies = await analytics.detect_anomalies(channel_id, window_hours, sensitivity)

    return {
        "channel_id": channel_id,
        "window_hours": window_hours,
        "sensitivity": sensitivity,
        "anomalies": [
            {
                "hormone": a.hormone_name,
                "type": a.anomaly_type,
                "severity": a.severity,
                "value": a.value,
                "expected": a.expected_value,
                "deviation_pct": ((a.value - a.expected_value) / a.expected_value * 100)
                if a.expected_value > 0
                else 0,
                "timestamp": a.timestamp.isoformat(),
                "context": a.context,
            }
            for a in anomalies
        ],
    }


@router.get("/hormones/correlations/{channel_id}")
async def hormone_correlations(
    channel_id: str,
    days: int = 7,
    level: int = 1,
) -> Dict:
    """
    Find correlations between hormones.

    Args:
        channel_id: Discord channel ID
        days: Days of history to analyze
        level: HIM pyramid level

    Returns:
        Hormone correlations with strength indicators
    """
    import datetime as dt

    analytics = create_analytics()
    end_time = dt.datetime.now(dt.timezone.utc)
    start_time = end_time - dt.timedelta(days=days)

    correlations = await analytics.analyze_correlations(channel_id, start_time, end_time, level)

    return {
        "channel_id": channel_id,
        "analysis_period_days": days,
        "correlations": [
            {
                "hormone_a": c.hormone_a,
                "hormone_b": c.hormone_b,
                "correlation": c.correlation,
                "relationship": c.relationship,
                "strength": c.strength,
            }
            for c in correlations
        ],
    }


@router.get("/hormones/circadian/{channel_id}")
async def circadian_patterns(
    channel_id: str,
    days: int = 7,
) -> Dict:
    """
    Detect circadian (time-of-day) patterns in hormones.

    Args:
        channel_id: Discord channel ID
        days: Days of history to analyze

    Returns:
        Circadian patterns with peak/trough times
    """
    analytics = create_analytics()
    patterns = await analytics.detect_circadian_patterns(channel_id, days)

    return {
        "channel_id": channel_id,
        "analysis_period_days": days,
        "patterns": [
            {
                "hormone": p.hormone_name,
                "peak_hour": p.peak_hour,
                "trough_hour": p.trough_hour,
                "amplitude": p.amplitude,
                "pattern_strength": p.pattern_strength,
                "interpretation": f"{p.hormone_name.title()} peaks at {p.peak_hour:02d}:00 and troughs at {p.trough_hour:02d}:00",
            }
            for p in patterns
        ],
    }


# Standalone app for running metrics server independently
def create_metrics_app():
    """Create standalone FastAPI app for metrics API."""
    from fastapi import FastAPI

    app = FastAPI(title="SEL Bot Metrics API")
    app.include_router(router)
    return app
