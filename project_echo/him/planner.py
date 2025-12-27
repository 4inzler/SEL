"""Query planner for the Hierarchical Image Memory service."""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from heapq import heappush, heapreplace, nlargest
from typing import Dict, List, Sequence

from .models import QueryHint, QueryPlan, QueryRequest, QueryTile, TileMeta
from .storage import HierarchicalImageMemory, TileUsage


@dataclass(slots=True)
class HintRegion:
    """Normalized bounding box extracted from a hint."""

    confidence: float
    x_min: int
    x_max: int
    y_min: int
    y_max: int


@dataclass(slots=True)
class TileScore:
    """Internal structure used for ranking candidate tiles."""

    priority: float
    tile: QueryTile
    hint_hits: float


class QueryPlanner:
    """Heuristic query planner that fuses hints and tile telemetry."""

    def __init__(self, store: HierarchicalImageMemory) -> None:
        self.store = store

    def plan(self, request: QueryRequest) -> QueryPlan:
        tiles = self.store.tiles_for_snapshot(
            request.snapshot_id,
            stream=request.stream,
            level_range=request.level_range,
        )
        if not tiles:
            return QueryPlan(tile_ids=[], acceptance=0.0, budget_ms=request.budget_ms)

        usage = self.store.tile_usage_for_snapshot(request.snapshot_id)
        hints = self.store.recent_hints(
            request.snapshot_id,
            stream=request.stream,
            limit=64,
            level_range=request.level_range,
        )
        hint_index = self._build_hint_index(hints, request.level_range)

        now = datetime.now(timezone.utc)
        max_candidates = max(request.max_tiles * 8, 32)
        heap: List[tuple[float, int, TileScore]] = []
        for idx, meta in enumerate(tiles):
            score_value, hint_strength = self._score_tile(
                meta,
                usage.get(meta.tile_id),
                hint_index.get(meta.level, ()),
                request.level_range,
                now,
            )
            score = TileScore(
                priority=score_value,
                hint_hits=hint_strength,
                tile=QueryTile(
                    tile_id=meta.tile_id,
                    stream=meta.stream,
                    snapshot_id=meta.snapshot_id,
                    level=meta.level,
                    x=meta.x,
                    y=meta.y,
                ),
            )
            entry = (score_value, idx, score)
            if len(heap) < max_candidates:
                heappush(heap, entry)
            elif score_value > heap[0][0]:
                heapreplace(heap, entry)

        if not heap:
            return QueryPlan(tile_ids=[], acceptance=0.0, budget_ms=request.budget_ms)

        top_entries = nlargest(request.max_tiles, heap)
        selected_scores = [item[2] for item in top_entries]
        selected_tiles = [item.tile for item in selected_scores]
        if not selected_tiles:
            return QueryPlan(tile_ids=[], acceptance=0.0, budget_ms=request.budget_ms)

        hint_hit_ratio = 0.0
        if selected_scores:
            hint_hit_ratio = sum(1 for item in selected_scores if item.hint_hits > 0.0) / len(
                selected_scores
            )
        acceptance = min(0.99, 0.55 + 0.08 * len(selected_scores) + 0.25 * hint_hit_ratio)
        return QueryPlan(tile_ids=selected_tiles, acceptance=acceptance, budget_ms=request.budget_ms)

    @staticmethod
    def _score_tile(
        meta: TileMeta,
        usage: TileUsage | None,
        hints: Sequence[HintRegion],
        level_range: Sequence[int],
        now: datetime,
    ) -> tuple[float, float]:
        max_level, min_level = level_range
        level_weight = (max_level - meta.level) * 3.0
        hotness = math.log1p(usage.access_count) * 2.0 if usage else 0.0
        recency = 0.0
        if usage and usage.last_access:
            age_minutes = (now - usage.last_access).total_seconds() / 60.0
            recency = max(0.0, 6.0 - age_minutes)
        hint_bonus = QueryPlanner._hint_bonus(meta, hints)
        distance_penalty = (abs(meta.x) + abs(meta.y)) * 0.25
        score = level_weight + hotness + recency + hint_bonus - distance_penalty
        return score, hint_bonus

    @staticmethod
    def _build_hint_index(
        hints: Sequence[QueryHint], level_range: Sequence[int]
    ) -> Dict[int, Sequence[HintRegion]]:
        if not hints:
            return {}
        max_level, min_level = level_range
        index: Dict[int, List[HintRegion]] = defaultdict(list)
        for hint in hints:
            hint_max, hint_min = hint.level_range
            upper = min(max_level, hint_max)
            lower = max(min_level, hint_min)
            if upper < lower:
                continue
            regions = tuple(
                QueryPlanner._normalize_bbox(bbox, hint.confidence)
                for bbox in hint.bboxes
            )
            for region in regions:
                if region is None:
                    continue
                for level in range(lower, upper + 1):
                    index[level].append(region)
        return {level: tuple(regions) for level, regions in index.items()}

    @staticmethod
    def _normalize_bbox(
        bbox: Sequence[int], confidence: float
    ) -> HintRegion | None:
        if len(bbox) != 4:
            return None
        x, y, w, h = bbox
        if w <= 0 or h <= 0:
            return None
        return HintRegion(
            confidence=confidence,
            x_min=x,
            x_max=x + w - 1,
            y_min=y,
            y_max=y + h - 1,
        )

    @staticmethod
    def _hint_bonus(meta: TileMeta, hints: Sequence[HintRegion]) -> float:
        bonus = 0.0
        for hint in hints:
            if QueryPlanner._tile_intersects_region(meta, hint):
                bonus += hint.confidence * 12.0
        return bonus

    @staticmethod
    def _tile_intersects_region(meta: TileMeta, region: HintRegion) -> bool:
        return (
            region.x_min <= meta.x <= region.x_max
            and region.y_min <= meta.y <= region.y_max
        )
