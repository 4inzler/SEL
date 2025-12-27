"""
Advanced hormone analytics using HIM's hierarchical storage capabilities.

Leverages HIM's multi-level pyramid structure for efficient historical analysis:
- L0 (finest): 5-minute snapshots for recent detailed analysis
- L1 (hourly): Aggregated hourly trends
- L2 (daily): Daily patterns and circadian rhythm analysis
- L3 (weekly): Long-term trends and behavioral patterns

Provides:
- Trend detection (rising/falling hormones over time)
- Anomaly detection (unusual hormone spikes/drops)
- Correlation analysis (which hormones move together)
- Predictive analytics (forecast future states based on patterns)
- Circadian rhythm analysis (time-of-day patterns)
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .hormones import HormoneVector

logger = logging.getLogger(__name__)


@dataclass
class HormoneTrend:
    """Detected trend in hormone levels over time."""

    hormone_name: str
    direction: str  # "rising", "falling", "stable"
    slope: float  # Rate of change per hour
    confidence: float  # 0.0-1.0 confidence in trend
    start_value: float
    end_value: float
    start_time: dt.datetime
    end_time: dt.datetime
    significance: str  # "major", "moderate", "minor"


@dataclass
class HormoneAnomaly:
    """Detected anomaly in hormone behavior."""

    hormone_name: str
    anomaly_type: str  # "spike", "drop", "oscillation"
    severity: float  # 0.0-1.0 how extreme
    value: float
    expected_value: float
    timestamp: dt.datetime
    context: str  # Human-readable explanation


@dataclass
class HormoneCorrelation:
    """Correlation between two hormones."""

    hormone_a: str
    hormone_b: str
    correlation: float  # -1.0 to 1.0 (Pearson correlation)
    relationship: str  # "positive", "negative", "none"
    strength: str  # "strong", "moderate", "weak"


@dataclass
class CircadianPattern:
    """Detected time-of-day pattern for a hormone."""

    hormone_name: str
    peak_hour: int  # 0-23
    trough_hour: int  # 0-23
    amplitude: float  # Difference between peak and trough
    pattern_strength: float  # 0.0-1.0 how consistent the pattern is


class HormoneAnalytics:
    """
    Advanced analytics engine for hormone data using HIM.

    Analyzes hormonal patterns across multiple time scales:
    - Short-term (hours): Immediate reactions and state changes
    - Medium-term (days): Daily patterns and rhythms
    - Long-term (weeks): Behavioral trends and personality evolution
    """

    def __init__(self, store=None):
        """
        Initialize analytics engine.

        Args:
            store: HierarchicalImageMemory instance (for testing)
        """
        if store is None:
            from him import HierarchicalImageMemory
            self.store = HierarchicalImageMemory(Path("./sel_data/him_store"))
        else:
            self.store = store

        self.stream = "hormonal_state"

    async def analyze_trends(
        self,
        channel_id: str,
        start_time: dt.datetime,
        end_time: dt.datetime,
        level: int = 1,  # Hourly resolution
    ) -> List[HormoneTrend]:
        """
        Detect trends in hormone levels over a time range.

        Args:
            channel_id: Discord channel ID
            start_time: Start of analysis period
            end_time: End of analysis period
            level: HIM pyramid level (0=5min, 1=hourly, 2=daily, 3=weekly)

        Returns:
            List of detected trends with confidence scores
        """
        from .hormone_state_manager import HormoneHistoryQuery

        query = HormoneHistoryQuery(self.store)
        snapshots = query.query_range(channel_id, start_time, end_time, level)

        if len(snapshots) < 3:
            logger.debug("Insufficient data for trend analysis (need >= 3 snapshots)")
            return []

        # Analyze each hormone independently
        trends = []
        hormone_names = [
            "dopamine",
            "serotonin",
            "cortisol",
            "oxytocin",
            "melatonin",
            "novelty",
            "curiosity",
            "patience",
            "estrogen",
            "testosterone",
            "adrenaline",
            "endorphin",
            "progesterone",
        ]

        for hormone_name in hormone_names:
            trend = self._analyze_hormone_trend(hormone_name, snapshots)
            if trend:
                trends.append(trend)

        # Sort by significance
        significance_order = {"major": 0, "moderate": 1, "minor": 2}
        trends.sort(key=lambda t: significance_order.get(t.significance, 3))

        return trends

    def _analyze_hormone_trend(
        self, hormone_name: str, snapshots: List[Dict]
    ) -> Optional[HormoneTrend]:
        """Analyze trend for a single hormone using linear regression."""
        values = []
        timestamps = []

        for snapshot in snapshots:
            hormones = snapshot.get("hormones", {})
            value = hormones.get(hormone_name)
            timestamp_str = snapshot.get("timestamp")

            if value is not None and timestamp_str:
                values.append(float(value))
                timestamps.append(dt.datetime.fromisoformat(timestamp_str))

        if len(values) < 3:
            return None

        # Simple linear regression: y = mx + b
        n = len(values)
        x = list(range(n))  # Time indices
        y = values

        x_mean = statistics.mean(x)
        y_mean = statistics.mean(y)

        numerator = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return None

        slope = numerator / denominator
        intercept = y_mean - slope * x_mean

        # Calculate R² (coefficient of determination)
        y_pred = [slope * xi + intercept for xi in x]
        ss_res = sum((y[i] - y_pred[i]) ** 2 for i in range(n))
        ss_tot = sum((y[i] - y_mean) ** 2 for i in range(n))
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

        # Determine direction
        if abs(slope) < 0.01:
            direction = "stable"
        elif slope > 0:
            direction = "rising"
        else:
            direction = "falling"

        # Determine significance based on slope magnitude and R²
        change_magnitude = abs(values[-1] - values[0])
        if change_magnitude > 0.3 and r_squared > 0.7:
            significance = "major"
        elif change_magnitude > 0.15 and r_squared > 0.5:
            significance = "moderate"
        else:
            significance = "minor"

        # Convert slope to per-hour rate
        time_span_hours = (timestamps[-1] - timestamps[0]).total_seconds() / 3600.0
        slope_per_hour = slope / (len(values) / time_span_hours) if time_span_hours > 0 else 0

        return HormoneTrend(
            hormone_name=hormone_name,
            direction=direction,
            slope=slope_per_hour,
            confidence=r_squared,
            start_value=values[0],
            end_value=values[-1],
            start_time=timestamps[0],
            end_time=timestamps[-1],
            significance=significance,
        )

    async def detect_anomalies(
        self,
        channel_id: str,
        window_hours: int = 24,
        sensitivity: float = 2.0,  # Standard deviations for anomaly threshold
    ) -> List[HormoneAnomaly]:
        """
        Detect unusual hormone spikes or drops in recent history.

        Args:
            channel_id: Discord channel ID
            window_hours: Hours of history to analyze
            sensitivity: Number of standard deviations to consider anomalous

        Returns:
            List of detected anomalies
        """
        from .hormone_state_manager import HormoneHistoryQuery

        end_time = dt.datetime.now(dt.timezone.utc)
        start_time = end_time - dt.timedelta(hours=window_hours)

        query = HormoneHistoryQuery(self.store)
        snapshots = query.query_range(channel_id, start_time, end_time, level=0)  # 5-min resolution

        if len(snapshots) < 10:
            return []

        anomalies = []
        hormone_names = [
            "dopamine",
            "serotonin",
            "cortisol",
            "oxytocin",
            "melatonin",
            "novelty",
            "curiosity",
            "patience",
        ]

        for hormone_name in hormone_names:
            values = []
            timestamps = []

            for snapshot in snapshots:
                hormones = snapshot.get("hormones", {})
                value = hormones.get(hormone_name)
                timestamp_str = snapshot.get("timestamp")

                if value is not None and timestamp_str:
                    values.append(float(value))
                    timestamps.append(dt.datetime.fromisoformat(timestamp_str))

            if len(values) < 10:
                continue

            # Calculate baseline statistics
            mean = statistics.mean(values)
            stdev = statistics.stdev(values) if len(values) > 1 else 0

            # Find anomalies
            for i, value in enumerate(values):
                if stdev == 0:
                    continue

                z_score = abs(value - mean) / stdev

                if z_score > sensitivity:
                    # Determine anomaly type
                    if value > mean:
                        anomaly_type = "spike"
                    else:
                        anomaly_type = "drop"

                    # Calculate severity
                    severity = min(1.0, (z_score - sensitivity) / sensitivity)

                    # Generate context
                    change_pct = ((value - mean) / mean) * 100 if mean > 0 else 0
                    context = f"{hormone_name.title()} {'increased' if value > mean else 'decreased'} by {abs(change_pct):.1f}%"

                    anomalies.append(
                        HormoneAnomaly(
                            hormone_name=hormone_name,
                            anomaly_type=anomaly_type,
                            severity=severity,
                            value=value,
                            expected_value=mean,
                            timestamp=timestamps[i],
                            context=context,
                        )
                    )

        # Sort by severity descending
        anomalies.sort(key=lambda a: a.severity, reverse=True)
        return anomalies[:10]  # Return top 10

    async def analyze_correlations(
        self,
        channel_id: str,
        start_time: dt.datetime,
        end_time: dt.datetime,
        level: int = 1,
    ) -> List[HormoneCorrelation]:
        """
        Find correlations between different hormones.

        Args:
            channel_id: Discord channel ID
            start_time: Start of analysis period
            end_time: End of analysis period
            level: HIM pyramid level

        Returns:
            List of significant hormone correlations
        """
        from .hormone_state_manager import HormoneHistoryQuery

        query = HormoneHistoryQuery(self.store)
        snapshots = query.query_range(channel_id, start_time, end_time, level)

        if len(snapshots) < 5:
            return []

        # Extract all hormone values
        hormone_series = {}
        hormone_names = ["dopamine", "serotonin", "cortisol", "oxytocin", "melatonin", "novelty", "curiosity", "patience"]

        for hormone_name in hormone_names:
            values = []
            for snapshot in snapshots:
                hormones = snapshot.get("hormones", {})
                value = hormones.get(hormone_name)
                if value is not None:
                    values.append(float(value))

            if len(values) == len(snapshots):  # Only include if we have complete data
                hormone_series[hormone_name] = values

        # Calculate pairwise correlations
        correlations = []
        analyzed_pairs = set()

        for hormone_a in hormone_series.keys():
            for hormone_b in hormone_series.keys():
                if hormone_a >= hormone_b:  # Skip self-correlation and duplicates
                    continue

                pair_key = tuple(sorted([hormone_a, hormone_b]))
                if pair_key in analyzed_pairs:
                    continue
                analyzed_pairs.add(pair_key)

                values_a = hormone_series[hormone_a]
                values_b = hormone_series[hormone_b]

                # Pearson correlation coefficient
                corr = self._calculate_correlation(values_a, values_b)

                # Determine relationship and strength
                if abs(corr) < 0.3:
                    relationship = "none"
                    strength = "weak"
                elif corr > 0:
                    relationship = "positive"
                    strength = "strong" if abs(corr) > 0.7 else "moderate"
                else:
                    relationship = "negative"
                    strength = "strong" if abs(corr) > 0.7 else "moderate"

                # Only include significant correlations
                if abs(corr) >= 0.5:
                    correlations.append(
                        HormoneCorrelation(
                            hormone_a=hormone_a,
                            hormone_b=hormone_b,
                            correlation=corr,
                            relationship=relationship,
                            strength=strength,
                        )
                    )

        # Sort by correlation strength
        correlations.sort(key=lambda c: abs(c.correlation), reverse=True)
        return correlations

    def _calculate_correlation(self, x: List[float], y: List[float]) -> float:
        """Calculate Pearson correlation coefficient."""
        if len(x) != len(y) or len(x) < 2:
            return 0.0

        n = len(x)
        mean_x = statistics.mean(x)
        mean_y = statistics.mean(y)

        numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        denominator_x = sum((x[i] - mean_x) ** 2 for i in range(n))
        denominator_y = sum((y[i] - mean_y) ** 2 for i in range(n))

        denominator = math.sqrt(denominator_x * denominator_y)

        if denominator == 0:
            return 0.0

        return numerator / denominator

    async def detect_circadian_patterns(
        self,
        channel_id: str,
        days: int = 7,
    ) -> List[CircadianPattern]:
        """
        Analyze time-of-day patterns in hormone levels.

        Args:
            channel_id: Discord channel ID
            days: Number of days of history to analyze

        Returns:
            List of detected circadian patterns
        """
        from .hormone_state_manager import HormoneHistoryQuery

        end_time = dt.datetime.now(dt.timezone.utc)
        start_time = end_time - dt.timedelta(days=days)

        query = HormoneHistoryQuery(self.store)
        snapshots = query.query_range(channel_id, start_time, end_time, level=1)  # Hourly

        if len(snapshots) < days * 12:  # Need at least 12 hours per day
            return []

        # Group by hour of day
        hormone_names = ["dopamine", "serotonin", "melatonin", "cortisol", "curiosity"]
        patterns = []

        for hormone_name in hormone_names:
            hourly_values = {}  # hour -> [values]

            for snapshot in snapshots:
                hormones = snapshot.get("hormones", {})
                value = hormones.get(hormone_name)
                timestamp_str = snapshot.get("timestamp")

                if value is not None and timestamp_str:
                    timestamp = dt.datetime.fromisoformat(timestamp_str)
                    hour = timestamp.hour

                    if hour not in hourly_values:
                        hourly_values[hour] = []
                    hourly_values[hour].append(float(value))

            if len(hourly_values) < 12:  # Need sufficient coverage
                continue

            # Calculate average for each hour
            hourly_averages = {hour: statistics.mean(values) for hour, values in hourly_values.items()}

            # Find peak and trough
            peak_hour = max(hourly_averages, key=hourly_averages.get)
            trough_hour = min(hourly_averages, key=hourly_averages.get)
            amplitude = hourly_averages[peak_hour] - hourly_averages[trough_hour]

            # Calculate pattern strength (consistency)
            # Higher standard deviation in hourly averages = stronger pattern
            if len(hourly_averages.values()) > 1:
                hourly_stdev = statistics.stdev(hourly_averages.values())
                pattern_strength = min(1.0, hourly_stdev / 0.5)  # Normalize
            else:
                pattern_strength = 0.0

            if amplitude > 0.1 and pattern_strength > 0.3:  # Significant pattern
                patterns.append(
                    CircadianPattern(
                        hormone_name=hormone_name,
                        peak_hour=peak_hour,
                        trough_hour=trough_hour,
                        amplitude=amplitude,
                        pattern_strength=pattern_strength,
                    )
                )

        return patterns


# Convenience function
def create_analytics(store=None) -> HormoneAnalytics:
    """Create a HormoneAnalytics instance."""
    return HormoneAnalytics(store)
