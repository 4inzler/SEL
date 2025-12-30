"""Rendering and analysis utilities for hierarchical image memory tiles."""
from __future__ import annotations

import colorsys
import importlib.util
import csv
import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw

_SKIMAGE_BASE = importlib.util.find_spec("skimage") is not None
_HAS_SKIMAGE = False
if _SKIMAGE_BASE:
    _SKIMAGE_METRICS = importlib.util.find_spec("skimage.metrics") is not None
    if _SKIMAGE_METRICS:
        from skimage.metrics import structural_similarity
        _HAS_SKIMAGE = True
if not _HAS_SKIMAGE:  # pragma: no cover - optional dependency
    structural_similarity = None

logger = logging.getLogger(__name__)


RenderKey = Tuple[str, str, int]


@dataclass(slots=True)
class TileShape:
    """Parsed shape payload extracted from a tile JSON blob."""

    raw: Dict[str, object]
    center: Optional[Tuple[float, float]]
    radius: Optional[float]
    fill: Optional[str]
    alpha: Optional[float]
    weight: Optional[float]
    uncertainty: Optional[float]
    vector: Optional[Tuple[float, float]]
    identifier: Optional[str]


@dataclass(slots=True)
class TileRecord:
    """Single tile discovered on disk."""

    dataset: str
    run_id: str
    level: int
    x: int
    y: int
    shapes: List[TileShape]
    source: Path


@dataclass(slots=True)
class CoordStats:
    """Coordinate statistics across an entire level."""

    min_x: float
    max_x: float
    min_y: float
    max_y: float
    max_radius: float
    normalized: bool


@dataclass(slots=True)
class LevelSpec:
    """Normalisation parameters and grid shape for a level."""

    nx: int
    ny: int
    coord_mode: str
    stats: CoordStats


@dataclass(slots=True)
class LevelLayout:
    """Aggregated tiles for a dataset/run_id/level trio."""

    dataset: str
    run_id: str
    level: int
    spec: LevelSpec
    tiles: Dict[Tuple[int, int], List[TileShape]]
    shape_count: int


@dataclass(slots=True)
class RenderShape:
    """Shape ready for world-space rendering."""

    center: Tuple[float, float]
    radius: float
    weight: Optional[float]
    uncertainty: Optional[float]
    fill: Optional[str]
    alpha: Optional[float]
    identifier: str
    vector: Optional[Tuple[float, float]]
    tile: Tuple[int, int]
    raw: Dict[str, object]


@dataclass(slots=True)
class MetricRecord:
    """Computed metrics for a rendered level."""

    dataset: str
    run_id: str
    level: int
    shape_count: int
    total_mass: float
    coverage: float
    center_of_mass: Tuple[float, float]
    spread: float


@dataclass(slots=True)
class RenderedLevel:
    """Rendered canvas and associated metrics."""

    image: Image.Image
    metrics: MetricRecord


@dataclass(slots=True)
class RenderResult:
    """Rendered assets for a directory root."""

    root: Path
    layouts: Dict[RenderKey, LevelLayout]
    renders: Dict[RenderKey, Dict[str, RenderedLevel]]


def discover_tiles(root: Path) -> List[TileRecord]:
    """Discover tiles stored under the provided root directory."""

    records: List[TileRecord] = []
    for dataset_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        dataset = dataset_dir.name
        for run_dir in sorted(p for p in dataset_dir.iterdir() if p.is_dir()):
            run_id = run_dir.name
            for level_dir in sorted(p for p in run_dir.glob("L*")):
                level = _parse_suffix(level_dir.name, "L")
                if level is None:
                    logger.warning("Skipping level directory with unexpected name: %s", level_dir)
                    continue
                for x_dir in sorted(p for p in level_dir.glob("x*") if p.is_dir()):
                    tile_x = _parse_suffix(x_dir.name, "x")
                    if tile_x is None:
                        logger.warning("Skipping tile directory with unexpected name: %s", x_dir)
                        continue
                    for y_dir in sorted(p for p in x_dir.glob("y*") if p.is_dir()):
                        tile_y = _parse_suffix(y_dir.name, "y")
                        if tile_y is None:
                            logger.warning("Skipping tile directory with unexpected name: %s", y_dir)
                            continue
                        shapes: List[TileShape] = []
                        for bin_path in sorted(y_dir.glob("*.bin")):
                            shapes.extend(_load_shapes(bin_path))
                        if not shapes:
                            continue
                        records.append(
                            TileRecord(
                                dataset=dataset,
                                run_id=run_id,
                                level=level,
                                x=tile_x,
                                y=tile_y,
                                shapes=shapes,
                                source=y_dir,
                            )
                        )
    return records


def build_layouts(records: Iterable[TileRecord], coord_mode: str = "auto") -> Dict[RenderKey, LevelLayout]:
    """Group tile records into renderable layouts."""

    grouped: Dict[RenderKey, List[TileRecord]] = {}
    for record in records:
        key = (record.dataset, record.run_id, record.level)
        grouped.setdefault(key, []).append(record)

    layouts: Dict[RenderKey, LevelLayout] = {}
    for key, tiles in grouped.items():
        nx = max(record.x for record in tiles) + 1
        ny = max(record.y for record in tiles) + 1
        stats = _compute_stats(tiles)
        resolved_mode = _resolve_coord_mode(coord_mode, stats)
        spec = LevelSpec(nx=nx, ny=ny, coord_mode=resolved_mode, stats=stats)
        tile_map: Dict[Tuple[int, int], List[TileShape]] = {}
        for record in tiles:
            tile_map[(record.x, record.y)] = record.shapes
        layouts[key] = LevelLayout(
            dataset=key[0],
            run_id=key[1],
            level=key[2],
            spec=spec,
            tiles=tile_map,
            shape_count=sum(len(tile.shapes) for tile in tiles),
        )
    return layouts


def merge_specs(primary: LevelSpec, secondary: LevelSpec | None) -> LevelSpec:
    """Combine specs so that two roots share identical world mapping."""

    if secondary is None:
        return primary
    stats = CoordStats(
        min_x=min(primary.stats.min_x, secondary.stats.min_x),
        max_x=max(primary.stats.max_x, secondary.stats.max_x),
        min_y=min(primary.stats.min_y, secondary.stats.min_y),
        max_y=max(primary.stats.max_y, secondary.stats.max_y),
        max_radius=max(primary.stats.max_radius, secondary.stats.max_radius),
        normalized=primary.stats.normalized and secondary.stats.normalized,
    )
    coord_mode = "normalized" if primary.coord_mode == secondary.coord_mode == "normalized" else "pixel"
    return LevelSpec(
        nx=max(primary.nx, secondary.nx),
        ny=max(primary.ny, secondary.ny),
        coord_mode=coord_mode,
        stats=stats,
    )


def render_layouts(
    layouts: Dict[RenderKey, LevelLayout],
    *,
    canvas_size: int = 1024,
    render_modes: Sequence[str] | None = None,
    spec_overrides: Dict[RenderKey, LevelSpec] | None = None,
) -> Dict[RenderKey, Dict[str, RenderedLevel]]:
    """Render every layout into stitched PNGs."""

    render_modes = tuple(render_modes or ("default",))
    results: Dict[RenderKey, Dict[str, RenderedLevel]] = {}
    for key, layout in layouts.items():
        spec = spec_overrides.get(key) if spec_overrides else None
        render_spec = spec or layout.spec
        shapes = _normalise_shapes(layout, render_spec)
        sorted_shapes = sorted(shapes, key=_shape_sort_key)
        renders: Dict[str, RenderedLevel] = {}
        for mode in render_modes:
            image = _render_shapes(sorted_shapes, render_spec, canvas_size=canvas_size, mode=mode)
            metrics = _compute_metrics(image, layout, mode=mode)
            renders[mode] = RenderedLevel(image=image, metrics=metrics)
        results[key] = renders
    return results


def write_metrics(metrics: Iterable[MetricRecord], output_dir: Path) -> None:
    """Persist metrics to JSON and CSV."""

    output_dir.mkdir(parents=True, exist_ok=True)
    metrics_list = list(metrics)
    json_path = output_dir / "metrics.json"
    csv_path = output_dir / "metrics.csv"

    json_path.write_text(json.dumps([_metric_to_dict(m) for m in metrics_list], indent=2))
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "dataset",
                "run_id",
                "level",
                "shape_count",
                "total_mass",
                "coverage",
                "center_x",
                "center_y",
                "spread",
            ]
        )
        for metric in metrics_list:
            writer.writerow(
                [
                    metric.dataset,
                    metric.run_id,
                    metric.level,
                    metric.shape_count,
                    f"{metric.total_mass:.6f}",
                    f"{metric.coverage:.6f}",
                    f"{metric.center_of_mass[0]:.6f}",
                    f"{metric.center_of_mass[1]:.6f}",
                    f"{metric.spread:.6f}",
                ]
            )


def diff_rendered_levels(
    first: RenderResult,
    second: RenderResult,
    *,
    output_dir: Path,
    render_modes: Sequence[str] | None = None,
    align_window: int = 0,
) -> Dict[RenderKey, Dict[str, Path]]:
    """Compare two roots and emit delta heatmaps."""

    render_modes = tuple(render_modes or ("default",))
    output_dir.mkdir(parents=True, exist_ok=True)
    saved: Dict[RenderKey, Dict[str, Path]] = {}
    keys = set(first.renders) & set(second.renders)
    for key in sorted(keys):
        first_modes = first.renders[key]
        second_modes = second.renders[key]
        available_modes = [mode for mode in render_modes if mode in first_modes and mode in second_modes]
        if not available_modes:
            continue
        default_mode = "default" if "default" in available_modes else available_modes[0]
        base_shift = _compute_shift(
            first_modes[default_mode].image,
            second_modes[default_mode].image,
            max_shift=align_window,
        )
        for mode in available_modes:
            delta = _delta_image(
                first_modes[mode].image,
                second_modes[mode].image,
                shift=base_shift,
            )
            dataset, run_id, level = key
            mode_dir = output_dir / dataset / run_id
            mode_dir.mkdir(parents=True, exist_ok=True)
            path = mode_dir / f"L{level}_{mode}_delta.png"
            delta.save(path)
            saved.setdefault(key, {})[mode] = path
    return saved


def consistency_checks(
    renders: Dict[RenderKey, Dict[str, RenderedLevel]],
    *,
    output_dir: Path,
    render_mode: str = "default",
) -> Dict[str, object]:
    """Compare coarse levels against downsampled finer levels."""

    report: List[Dict[str, object]] = []
    output_dir.mkdir(parents=True, exist_ok=True)
    by_dataset: Dict[Tuple[str, str], Dict[int, RenderedLevel]] = {}
    for (dataset, run_id, level), modes in renders.items():
        level_map = by_dataset.setdefault((dataset, run_id), {})
        if render_mode in modes:
            level_map[level] = modes[render_mode]
    for (dataset, run_id), level_map in by_dataset.items():
        for level in sorted(level_map):
            if level == 0 or (level - 1) not in level_map:
                continue
            coarse = level_map[level].image
            fine = level_map[level - 1].image
            predicted = fine.resize(coarse.size, Image.BOX)
            mse, ssim = _image_similarity(predicted, coarse)
            delta = _delta_image(predicted, coarse, shift=(0, 0))
            pair_dir = output_dir / dataset / run_id
            pair_dir.mkdir(parents=True, exist_ok=True)
            delta_path = pair_dir / f"L{level}_consistency.png"
            delta.save(delta_path)
            entry = {
                "dataset": dataset,
                "run_id": run_id,
                "coarse_level": level,
                "fine_level": level - 1,
                "mse": mse,
                "ssim": ssim,
                "disagreement_map": str(delta_path),
            }
            report.append(entry)
    (output_dir / "consistency.json").write_text(json.dumps(report, indent=2))
    return {"pairs": report}


def _metric_to_dict(metric: MetricRecord) -> Dict[str, object]:
    return {
        "dataset": metric.dataset,
        "run_id": metric.run_id,
        "level": metric.level,
        "shape_count": metric.shape_count,
        "total_mass": metric.total_mass,
        "coverage": metric.coverage,
        "center_of_mass": list(metric.center_of_mass),
        "spread": metric.spread,
    }


def _image_similarity(predicted: Image.Image, actual: Image.Image) -> Tuple[float, Optional[float]]:
    a = np.asarray(predicted).astype(np.float32)
    b = np.asarray(actual).astype(np.float32)
    diff = a - b
    mse = float(np.mean(np.square(diff)))
    ssim_val: Optional[float] = None
    if structural_similarity is not None:
        try:
            ssim_val = float(
                structural_similarity(
                    np.asarray(predicted.convert("L")),
                    np.asarray(actual.convert("L")),
                )
            )
        except Exception as exc:  # pragma: no cover - optional dependency
            logger.warning("Failed to compute SSIM: %s", exc)
    return mse, ssim_val


def _delta_image(first: Image.Image, second: Image.Image, *, shift: Tuple[int, int]) -> Image.Image:
    a = np.asarray(first).astype(np.int16)
    b = np.asarray(second).astype(np.int16)
    b_shifted = _apply_shift(b, shift)
    diff = np.abs(a - b_shifted)
    summed = diff.sum(axis=2)
    clipped = np.clip(summed, 0, 255).astype(np.uint8)
    heatmap = np.zeros((*clipped.shape, 4), dtype=np.uint8)
    heatmap[..., 0] = clipped
    heatmap[..., 3] = np.clip(clipped * 2, 0, 255)
    return Image.fromarray(heatmap, mode="RGBA")


def _apply_shift(array: np.ndarray, shift: Tuple[int, int]) -> np.ndarray:
    dx, dy = shift
    h, w = array.shape[:2]
    shifted = np.zeros_like(array)
    x_src_start = max(0, -dx)
    x_src_end = w if dx < 0 else max(0, min(w, w - dx))
    y_src_start = max(0, -dy)
    y_src_end = h if dy < 0 else max(0, min(h, h - dy))
    x_dst_start = max(0, dx)
    x_dst_end = x_dst_start + max(0, x_src_end - x_src_start)
    y_dst_start = max(0, dy)
    y_dst_end = y_dst_start + max(0, y_src_end - y_src_start)
    if x_src_end <= x_src_start or y_src_end <= y_src_start:
        return shifted
    shifted[y_dst_start:y_dst_end, x_dst_start:x_dst_end] = array[
        y_src_start:y_src_end, x_src_start:x_src_end
    ]
    return shifted


def _compute_shift(first: Image.Image, second: Image.Image, *, max_shift: int) -> Tuple[int, int]:
    if max_shift <= 0:
        return (0, 0)
    a = np.asarray(first.convert("L")).astype(np.float32)
    b = np.asarray(second.convert("L")).astype(np.float32)
    best = (0, 0, -np.inf)
    for dx in range(-max_shift, max_shift + 1):
        for dy in range(-max_shift, max_shift + 1):
            shifted = _apply_shift(b, (dx, dy))
            score = float(np.sum(a * shifted))
            if score > best[2]:
                best = (dx, dy, score)
    return (best[0], best[1])


def _compute_metrics(image: Image.Image, layout: LevelLayout, *, mode: str) -> MetricRecord:
    arr = np.asarray(image).astype(np.float32) / 255.0
    alpha = arr[..., 3]
    mass = float(alpha.sum())
    coverage = float(np.count_nonzero(alpha)) / alpha.size if alpha.size else 0.0
    if mass > 0:
        h, w = alpha.shape
        xs, ys = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
        cx = float((alpha * xs).sum() / mass) / max(w - 1, 1)
        cy = float((alpha * ys).sum() / mass) / max(h - 1, 1)
        dx2 = (xs - cx * (w - 1)) ** 2
        dy2 = (ys - cy * (h - 1)) ** 2
        spread = float(((dx2 + dy2) * alpha).sum() / mass)
    else:
        cx = cy = 0.5
        spread = 0.0
    return MetricRecord(
        dataset=layout.dataset,
        run_id=layout.run_id,
        level=layout.level,
        shape_count=layout.shape_count,
        total_mass=mass,
        coverage=coverage,
        center_of_mass=(cx, cy),
        spread=spread,
    )


def _render_shapes(
    shapes: Sequence[RenderShape],
    spec: LevelSpec,
    *,
    canvas_size: int,
    mode: str,
) -> Image.Image:
    image = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    for shape in shapes:
        color, alpha, outline = _color_for_shape(shape, mode)
        if alpha <= 0:
            continue
        px, py, radius_px = _world_to_pixels(shape.center, shape.radius, spec, canvas_size)
        layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer, "RGBA")
        bbox = [px - radius_px, py - radius_px, px + radius_px, py + radius_px]
        draw.ellipse(bbox, fill=(*color, alpha), outline=outline)
        if mode == "vectors" and shape.vector is not None:
            vx_world, vy_world = shape.vector
            vx_px = vx_world * canvas_size
            vy_px = vy_world * canvas_size
            end = (px + vx_px, py + vy_px)
            draw.line([(px, py), end], fill=(*color, alpha), width=max(1, radius_px // 2))
        image = Image.alpha_composite(image, layer)
    return image


def _world_to_pixels(
    center: Tuple[float, float],
    radius: float,
    spec: LevelSpec,
    canvas_size: int,
) -> Tuple[int, int, int]:
    px = int(np.clip(center[0], 0.0, 1.0) * (canvas_size - 1))
    py = int(np.clip(center[1], 0.0, 1.0) * (canvas_size - 1))
    radius_px = int(max(1, radius * max(spec.nx, spec.ny) * canvas_size))
    return px, py, radius_px


def _color_for_shape(
    shape: RenderShape,
    mode: str,
) -> Tuple[Tuple[int, int, int], int, Optional[Tuple[int, int, int, int]]]:
    base_color = _parse_color(shape.fill) or _fallback_color(shape.identifier)
    alpha_val = shape.alpha if shape.alpha is not None else 0.8
    outline: Optional[Tuple[int, int, int, int]] = None
    if mode == "weight" and shape.weight is not None:
        alpha_val = _clamp01(shape.weight)
    elif mode == "uncertainty" and shape.uncertainty is not None:
        alpha_val = _clamp01(1.0 - shape.uncertainty)
        outline = (255, 128, 0, int(alpha_val * 255))
    alpha = int(_clamp01(alpha_val) * 255)
    return base_color, alpha, outline


def _normalise_shapes(layout: LevelLayout, spec: LevelSpec) -> List[RenderShape]:
    shapes: List[RenderShape] = []
    stats = spec.stats
    span_x = max(stats.max_x - stats.min_x, 1e-9)
    span_y = max(stats.max_y - stats.min_y, 1e-9)
    span_r = max(stats.max_radius, 1e-9)
    for (tile_x, tile_y), tile_shapes in layout.tiles.items():
        for shape in tile_shapes:
            if shape.center is None:
                continue
            cx, cy = shape.center
            radius = shape.radius or 0.0
            if spec.coord_mode == "pixel":
                cx_norm = (cx - stats.min_x) / span_x
                cy_norm = (cy - stats.min_y) / span_y
                r_norm = radius / max(span_r, span_x, span_y)
                vector = _normalise_vector(shape.vector, span_x, span_y, spec)
            else:
                cx_norm = cx
                cy_norm = cy
                r_norm = radius
                vector = _normalise_vector(shape.vector, 1.0, 1.0, spec)
            world_x = (tile_x + cx_norm) / spec.nx
            world_y = (tile_y + cy_norm) / spec.ny
            world_r = r_norm / max(spec.nx, spec.ny)
            identifier = shape.identifier or _stable_hash(shape.raw)
            shapes.append(
                RenderShape(
                    center=(world_x, world_y),
                    radius=world_r,
                    weight=shape.weight,
                    uncertainty=shape.uncertainty,
                    fill=shape.fill,
                    alpha=shape.alpha,
                    identifier=identifier,
                    vector=vector,
                    tile=(tile_x, tile_y),
                    raw=shape.raw,
                )
            )
    return shapes


def _normalise_vector(
    vector: Optional[Tuple[float, float]],
    span_x: float,
    span_y: float,
    spec: LevelSpec,
) -> Optional[Tuple[float, float]]:
    if vector is None:
        return None
    vx_norm = vector[0] / span_x
    vy_norm = vector[1] / span_y
    return (vx_norm / spec.nx, vy_norm / spec.ny)


def _shape_sort_key(shape: RenderShape) -> Tuple[str, float, float, float]:
    return (shape.identifier, shape.center[0], shape.center[1], shape.radius)


def _compute_stats(tiles: Iterable[TileRecord]) -> CoordStats:
    min_x = float("inf")
    max_x = float("-inf")
    min_y = float("inf")
    max_y = float("-inf")
    max_r = 0.0
    normalized = True
    for record in tiles:
        for shape in record.shapes:
            if shape.center is None:
                continue
            cx, cy = shape.center
            r = shape.radius or 0.0
            min_x = min(min_x, cx - r)
            max_x = max(max_x, cx + r)
            min_y = min(min_y, cy - r)
            max_y = max(max_y, cy + r)
            max_r = max(max_r, r)
            if (
                cx < -0.01
                or cy < -0.01
                or cx > 1.01
                or cy > 1.01
                or r > 1.01
            ):
                normalized = False
    if min_x == float("inf"):
        min_x = min_y = 0.0
        max_x = max_y = 1.0
    return CoordStats(min_x=min_x, max_x=max_x, min_y=min_y, max_y=max_y, max_radius=max_r, normalized=normalized)


def _resolve_coord_mode(coord_mode: str, stats: CoordStats) -> str:
    if coord_mode in {"normalized", "pixel"}:
        return coord_mode
    if coord_mode != "auto":
        logger.warning("Unknown coord mode '%s'; defaulting to auto", coord_mode)
    return "normalized" if stats.normalized else "pixel"


def _load_shapes(bin_path: Path) -> List[TileShape]:
    try:
        payload = json.loads(bin_path.read_text())
    except Exception as exc:
        logger.warning("Failed to parse %s: %s", bin_path, exc)
        return []
    shapes = payload.get("shapes")
    if not isinstance(shapes, list):
        logger.warning("Tile payload missing shapes list: %s", bin_path)
        return []
    parsed: List[TileShape] = []
    for idx, raw_shape in enumerate(shapes):
        if not isinstance(raw_shape, dict):
            logger.warning("Skipping malformed shape %s in %s", idx, bin_path)
            continue
        center = _parse_point(raw_shape.get("center"))
        radius = _parse_float(raw_shape.get("radius"))
        identifier = raw_shape.get("id")
        vector = _parse_point(raw_shape.get("vector") or raw_shape.get("direction"))
        parsed.append(
            TileShape(
                raw=raw_shape,
                center=center,
                radius=radius,
                fill=raw_shape.get("fill"),
                alpha=_parse_float(raw_shape.get("alpha")),
                weight=_parse_float(raw_shape.get("weight")),
                uncertainty=_parse_float(raw_shape.get("uncertainty")),
                vector=vector,
                identifier=identifier if isinstance(identifier, str) else None,
            )
        )
    return parsed


def _parse_point(value: object) -> Optional[Tuple[float, float]]:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        try:
            return float(value[0]), float(value[1])
        except (TypeError, ValueError):
            return None
    return None


def _parse_float(value: object) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_suffix(name: str, prefix: str) -> Optional[int]:
    try:
        return int(name.removeprefix(prefix))
    except ValueError:
        return None


def _stable_hash(data: Dict[str, object]) -> str:
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.blake2b(encoded, digest_size=8).hexdigest()


def _fallback_color(identifier: str) -> Tuple[int, int, int]:
    digest = hashlib.blake2b(identifier.encode("utf-8"), digest_size=6).digest()
    hue = int.from_bytes(digest[:2], "big") / 65535.0
    sat = 0.65 + (digest[2] / 255.0) * 0.2
    val = 0.6 + (digest[3] / 255.0) * 0.35
    r, g, b = colorsys.hsv_to_rgb(hue, min(sat, 1.0), min(val, 1.0))
    return (int(r * 255), int(g * 255), int(b * 255))


def _parse_color(value: Optional[str]) -> Optional[Tuple[int, int, int]]:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.startswith("#"):
        text = text[1:]
    if len(text) == 6:
        try:
            r = int(text[0:2], 16)
            g = int(text[2:4], 16)
            b = int(text[4:6], 16)
            return (r, g, b)
        except ValueError:
            return None
    return None


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


__all__ = [
    "CoordStats",
    "LevelLayout",
    "LevelSpec",
    "MetricRecord",
    "RenderResult",
    "RenderShape",
    "RenderedLevel",
    "TileRecord",
    "TileShape",
    "consistency_checks",
    "diff_rendered_levels",
    "discover_tiles",
    "merge_specs",
    "render_layouts",
    "build_layouts",
    "write_metrics",
]
