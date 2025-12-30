"""
Real-time performance monitoring and metrics collection for SEL bot.

Tracks latency, throughput, and resource usage across all subsystems:
- LLM API calls (response time, token usage, cache hits)
- HIM operations (query time, tile access, memory recall)
- Agent execution (run time, success rate, parallelism)
- Hormone system (update frequency, persistence time)
- Discord events (message processing latency)

Designed for production observability with minimal overhead.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetric:
    """Single performance measurement."""

    subsystem: str  # e.g., "llm", "him", "agent", "hormone", "discord"
    operation: str  # e.g., "generate_reply", "query_tiles", "run_agent"
    duration_ms: float
    success: bool
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, any] = field(default_factory=dict)


@dataclass
class SubsystemStats:
    """Aggregated statistics for a subsystem."""

    subsystem: str
    total_operations: int = 0
    successful_operations: int = 0
    failed_operations: int = 0
    total_duration_ms: float = 0.0
    min_duration_ms: float = float("inf")
    max_duration_ms: float = 0.0
    p50_duration_ms: float = 0.0
    p95_duration_ms: float = 0.0
    p99_duration_ms: float = 0.0

    @property
    def success_rate(self) -> float:
        """Success rate as percentage."""
        if self.total_operations == 0:
            return 0.0
        return (self.successful_operations / self.total_operations) * 100.0

    @property
    def avg_duration_ms(self) -> float:
        """Average operation duration."""
        if self.total_operations == 0:
            return 0.0
        return self.total_duration_ms / self.total_operations


class PerformanceMonitor:
    """
    Real-time performance monitoring with rolling windows and percentile calculations.

    Features:
    - Sub-millisecond overhead context managers
    - Rolling window keeps last N metrics per subsystem
    - Automatic percentile calculation (p50, p95, p99)
    - Thread-safe with asyncio locks
    - Export capabilities for external monitoring systems
    """

    def __init__(
        self,
        window_size: int = 1000,  # Keep last 1000 metrics per subsystem
        enable_detailed_logging: bool = False,
    ):
        self._metrics: Dict[str, Deque[PerformanceMetric]] = defaultdict(
            lambda: deque(maxlen=window_size)
        )
        self._lock = asyncio.Lock()
        self.window_size = window_size
        self.enable_detailed_logging = enable_detailed_logging

        # High-level counters (no rolling window)
        self._total_operations = 0
        self._total_errors = 0

    @asynccontextmanager
    async def measure(
        self,
        subsystem: str,
        operation: str,
        metadata: Optional[Dict[str, any]] = None,
    ):
        """
        Context manager for measuring operation performance.

        Usage:
            async with monitor.measure("llm", "generate_reply", {"model": "claude"}):
                response = await llm_client.generate_reply(...)
        """
        start_time = time.perf_counter()
        success = True
        error = None

        try:
            yield
        except Exception as exc:
            success = False
            error = str(exc)
            raise
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000.0

            metric = PerformanceMetric(
                subsystem=subsystem,
                operation=operation,
                duration_ms=duration_ms,
                success=success,
                metadata=metadata or {},
            )

            if error:
                metric.metadata["error"] = error

            await self._record_metric(metric)

            if self.enable_detailed_logging:
                status = "✓" if success else "✗"
                logger.debug(
                    "%s %s.%s completed in %.2fms",
                    status,
                    subsystem,
                    operation,
                    duration_ms,
                )

    async def _record_metric(self, metric: PerformanceMetric) -> None:
        """Store metric in rolling window."""
        async with self._lock:
            key = f"{metric.subsystem}.{metric.operation}"
            self._metrics[key].append(metric)

            self._total_operations += 1
            if not metric.success:
                self._total_errors += 1

    async def get_subsystem_stats(self, subsystem: str) -> SubsystemStats:
        """Get aggregated statistics for a subsystem."""
        async with self._lock:
            # Collect all metrics for this subsystem
            all_metrics: List[PerformanceMetric] = []
            for key, metrics in self._metrics.items():
                if key.startswith(f"{subsystem}."):
                    all_metrics.extend(metrics)

            if not all_metrics:
                return SubsystemStats(subsystem=subsystem)

            # Calculate statistics
            stats = SubsystemStats(subsystem=subsystem)
            stats.total_operations = len(all_metrics)
            stats.successful_operations = sum(1 for m in all_metrics if m.success)
            stats.failed_operations = stats.total_operations - stats.successful_operations

            durations = [m.duration_ms for m in all_metrics]
            stats.total_duration_ms = sum(durations)
            stats.min_duration_ms = min(durations)
            stats.max_duration_ms = max(durations)

            # Calculate percentiles
            sorted_durations = sorted(durations)
            n = len(sorted_durations)
            stats.p50_duration_ms = sorted_durations[int(n * 0.50)]
            stats.p95_duration_ms = sorted_durations[int(n * 0.95)]
            stats.p99_duration_ms = sorted_durations[int(n * 0.99)]

            return stats

    async def get_operation_stats(self, subsystem: str, operation: str) -> Dict:
        """Get detailed statistics for a specific operation."""
        async with self._lock:
            key = f"{subsystem}.{operation}"
            metrics = self._metrics.get(key, deque())

            if not metrics:
                return {
                    "subsystem": subsystem,
                    "operation": operation,
                    "total_operations": 0,
                }

            durations = [m.duration_ms for m in metrics]
            successful = sum(1 for m in metrics if m.success)

            sorted_durations = sorted(durations)
            n = len(sorted_durations)

            return {
                "subsystem": subsystem,
                "operation": operation,
                "total_operations": len(metrics),
                "successful_operations": successful,
                "failed_operations": len(metrics) - successful,
                "success_rate_pct": (successful / len(metrics)) * 100.0,
                "avg_duration_ms": sum(durations) / len(durations),
                "min_duration_ms": min(durations),
                "max_duration_ms": max(durations),
                "p50_duration_ms": sorted_durations[int(n * 0.50)],
                "p95_duration_ms": sorted_durations[int(n * 0.95)],
                "p99_duration_ms": sorted_durations[int(n * 0.99)],
            }

    async def get_all_stats(self) -> Dict[str, any]:
        """Get comprehensive statistics for all subsystems."""
        async with self._lock:
            # Extract unique subsystems
            subsystems = set()
            for key in self._metrics.keys():
                subsystem = key.split(".")[0]
                subsystems.add(subsystem)

            stats = {
                "overview": {
                    "total_operations": self._total_operations,
                    "total_errors": self._total_errors,
                    "error_rate_pct": (
                        (self._total_errors / self._total_operations) * 100.0
                        if self._total_operations > 0
                        else 0.0
                    ),
                },
                "subsystems": {},
            }

            for subsystem in subsystems:
                subsystem_stats = await self.get_subsystem_stats(subsystem)
                stats["subsystems"][subsystem] = {
                    "total_operations": subsystem_stats.total_operations,
                    "success_rate_pct": subsystem_stats.success_rate,
                    "avg_duration_ms": subsystem_stats.avg_duration_ms,
                    "p50_duration_ms": subsystem_stats.p50_duration_ms,
                    "p95_duration_ms": subsystem_stats.p95_duration_ms,
                    "p99_duration_ms": subsystem_stats.p99_duration_ms,
                }

            return stats

    async def get_slow_operations(self, threshold_ms: float = 1000.0) -> List[Dict]:
        """Find operations that exceed a duration threshold."""
        async with self._lock:
            slow_ops = []
            for key, metrics in self._metrics.items():
                for metric in metrics:
                    if metric.duration_ms > threshold_ms:
                        subsystem, operation = key.split(".", 1)
                        slow_ops.append(
                            {
                                "subsystem": subsystem,
                                "operation": operation,
                                "duration_ms": metric.duration_ms,
                                "timestamp": metric.timestamp,
                                "metadata": metric.metadata,
                            }
                        )

            # Sort by duration descending
            slow_ops.sort(key=lambda x: x["duration_ms"], reverse=True)
            return slow_ops

    async def export_prometheus_metrics(self) -> str:
        """Export metrics in Prometheus text format."""
        stats = await self.get_all_stats()
        lines = []

        # Overview metrics
        lines.append("# HELP sel_operations_total Total number of operations")
        lines.append("# TYPE sel_operations_total counter")
        lines.append(f'sel_operations_total {stats["overview"]["total_operations"]}')

        lines.append("# HELP sel_errors_total Total number of errors")
        lines.append("# TYPE sel_errors_total counter")
        lines.append(f'sel_errors_total {stats["overview"]["total_errors"]}')

        # Per-subsystem metrics
        for subsystem, sub_stats in stats["subsystems"].items():
            lines.append(
                f"# HELP sel_{subsystem}_duration_ms Operation duration in milliseconds"
            )
            lines.append(f"# TYPE sel_{subsystem}_duration_ms summary")
            lines.append(
                f'sel_{subsystem}_duration_ms{{quantile="0.5"}} {sub_stats["p50_duration_ms"]}'
            )
            lines.append(
                f'sel_{subsystem}_duration_ms{{quantile="0.95"}} {sub_stats["p95_duration_ms"]}'
            )
            lines.append(
                f'sel_{subsystem}_duration_ms{{quantile="0.99"}} {sub_stats["p99_duration_ms"]}'
            )

        return "\n".join(lines)


# Global singleton
_global_monitor: Optional[PerformanceMonitor] = None


def get_monitor() -> PerformanceMonitor:
    """Get or create the global performance monitor."""
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = PerformanceMonitor()
    return _global_monitor
