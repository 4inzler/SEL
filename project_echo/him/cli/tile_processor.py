"""CLI tool for directory-based HIM tile processing, rendering, and analysis.

Supports:
- Directory-based ingestion (episodic_vector, hormonal_state datasets)
- Canonical world-space mapping with configurable coord modes
- Stitched per-level PNG rendering with deterministic ordering
- Multiple render modes (default, weight, uncertainty, vectors)
- Diff support with delta heatmaps
- Metrics computation (JSON + CSV output)
- Multi-resolution consistency checks
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import math
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Data structures
# -----------------------------------------------------------------------------

@dataclass(slots=True)
class Shape:
    """A single shape parsed from a .bin file."""
    kind: str
    center: Tuple[float, float]
    radius: float
    fill: Optional[str] = None
    alpha: float = 1.0
    weight: float = 1.0
    channel: Optional[str] = None
    uncertainty: float = 0.0
    id: Optional[str] = None
    # Additional fields stored but not actively used
    extra: Dict[str, Any] = field(default_factory=dict)

    def stable_hash(self) -> str:
        """Compute a stable hash of this shape for deterministic sorting."""
        # Create a deterministic string representation
        data = json.dumps({
            "kind": self.kind,
            "center": list(self.center),
            "radius": self.radius,
            "fill": self.fill,
            "alpha": self.alpha,
            "weight": self.weight,
            "channel": self.channel,
            "uncertainty": self.uncertainty,
        }, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()


@dataclass(slots=True)
class TileData:
    """Parsed tile data from a .bin file."""
    tile_x: int
    tile_y: int
    level: int
    shapes: List[Shape]
    source_path: Path


@dataclass(slots=True)
class LevelInfo:
    """Information about a specific level in the tile grid."""
    level: int
    nx: int  # max(tile_x) + 1
    ny: int  # max(tile_y) + 1
    tiles: List[TileData]


@dataclass(slots=True)
class DatasetInfo:
    """Information about a dataset (episodic_vector or hormonal_state)."""
    name: str
    run_id: str
    levels: Dict[int, LevelInfo]


@dataclass(slots=True)
class Metrics:
    """Computed metrics for a dataset/run_id/level."""
    dataset: str
    run_id: str
    level: int
    shape_count: int
    total_mass: float
    coverage: float
    center_of_mass: Tuple[float, float]
    spread: float  # second moment / std deviation


# -----------------------------------------------------------------------------
# Coordinate modes
# -----------------------------------------------------------------------------

class CoordMode:
    AUTO = "auto"
    NORMALIZED = "normalized"
    PIXEL = "pixel"


# -----------------------------------------------------------------------------
# Directory discovery and parsing
# -----------------------------------------------------------------------------

def discover_datasets(root: Path) -> List[str]:
    """Discover dataset directories (episodic_vector, hormonal_state, etc.)."""
    if not root.is_dir():
        return []
    datasets = []
    for entry in root.iterdir():
        if entry.is_dir() and not entry.name.startswith('.'):
            # Check if it contains run_id subdirectories with level structure
            for child in entry.iterdir():
                if child.is_dir():
                    # Check for L{n} subdirectories
                    for subchild in child.iterdir():
                        if subchild.is_dir() and subchild.name.startswith('L'):
                            datasets.append(entry.name)
                            break
                    break
    return sorted(set(datasets))


def discover_run_ids(root: Path, dataset: str) -> List[str]:
    """Discover run_id directories within a dataset."""
    dataset_dir = root / dataset
    if not dataset_dir.is_dir():
        return []
    run_ids = []
    for entry in dataset_dir.iterdir():
        if entry.is_dir() and not entry.name.startswith('.'):
            # Verify it has level subdirectories
            for child in entry.iterdir():
                if child.is_dir() and child.name.startswith('L'):
                    run_ids.append(entry.name)
                    break
    return sorted(run_ids)


def discover_levels(root: Path, dataset: str, run_id: str) -> List[int]:
    """Discover levels within a run_id directory."""
    run_dir = root / dataset / run_id
    if not run_dir.is_dir():
        return []
    levels = []
    for entry in run_dir.iterdir():
        if entry.is_dir() and entry.name.startswith('L'):
            try:
                level = int(entry.name[1:])
                levels.append(level)
            except ValueError:
                continue
    return sorted(levels)


def parse_shape(shape_dict: Dict[str, Any]) -> Optional[Shape]:
    """Parse a shape dictionary from a .bin JSON file."""
    try:
        kind = shape_dict.get("kind", "circle")
        
        # Handle center - may be "center" or derived from "points"
        center = shape_dict.get("center")
        if center is None:
            # Try to derive from points
            points = shape_dict.get("points", [])
            if points and len(points) >= 1:
                if isinstance(points[0], (list, tuple)):
                    # Average all points
                    xs = [p[0] for p in points]
                    ys = [p[1] for p in points]
                    center = [sum(xs) / len(xs), sum(ys) / len(ys)]
                else:
                    center = [0.5, 0.5]
            else:
                center = [0.5, 0.5]
        
        if not isinstance(center, (list, tuple)) or len(center) < 2:
            center = [0.5, 0.5]
        
        # Handle radius
        radius = shape_dict.get("radius", 0.1)
        if radius is None:
            radius = 0.1
        
        # Optional fields
        fill = shape_dict.get("fill")
        alpha = float(shape_dict.get("alpha", 1.0))
        weight = float(shape_dict.get("weight", 1.0))
        channel = shape_dict.get("channel")
        uncertainty = float(shape_dict.get("uncertainty", 0.0))
        shape_id = shape_dict.get("id")
        
        # Collect extra fields
        known_keys = {"kind", "center", "radius", "fill", "alpha", "weight", 
                      "channel", "uncertainty", "id", "points"}
        extra = {k: v for k, v in shape_dict.items() if k not in known_keys}
        
        return Shape(
            kind=str(kind),
            center=(float(center[0]), float(center[1])),
            radius=float(radius),
            fill=fill,
            alpha=alpha,
            weight=weight,
            channel=channel,
            uncertainty=uncertainty,
            id=str(shape_id) if shape_id is not None else None,
            extra=extra,
        )
    except Exception as e:
        logger.warning("Failed to parse shape: %s - %s", shape_dict, e)
        return None


def load_bin_file(path: Path) -> Optional[Dict[str, Any]]:
    """Load a .bin file (JSON content despite extension)."""
    try:
        content = path.read_bytes()
        return json.loads(content.decode('utf-8'))
    except json.JSONDecodeError as e:
        logger.warning("Invalid JSON in %s: %s", path, e)
        return None
    except Exception as e:
        logger.warning("Failed to read %s: %s", path, e)
        return None


def iter_tile_files(level_dir: Path) -> Iterator[Tuple[int, int, Path]]:
    """Iterate over tile files in a level directory.
    
    Expected structure: L{level}/x{tile_x}/y{tile_y}/*.bin
    """
    if not level_dir.is_dir():
        return
    
    for x_dir in level_dir.iterdir():
        if not x_dir.is_dir() or not x_dir.name.startswith('x'):
            continue
        try:
            tile_x = int(x_dir.name[1:])
        except ValueError:
            continue
        
        for y_dir in x_dir.iterdir():
            if not y_dir.is_dir() or not y_dir.name.startswith('y'):
                continue
            try:
                tile_y = int(y_dir.name[1:])
            except ValueError:
                continue
            
            for bin_file in y_dir.glob('*.bin'):
                yield tile_x, tile_y, bin_file


def load_tiles_for_level(
    root: Path,
    dataset: str,
    run_id: str,
    level: int,
) -> List[TileData]:
    """Load all tiles for a specific level."""
    level_dir = root / dataset / run_id / f"L{level}"
    tiles: List[TileData] = []
    
    for tile_x, tile_y, bin_path in iter_tile_files(level_dir):
        data = load_bin_file(bin_path)
        if data is None:
            continue
        
        # Parse shapes
        shapes_data = data.get("shapes", [])
        if not isinstance(shapes_data, list):
            logger.warning("Invalid shapes in %s: not a list", bin_path)
            continue
        
        shapes = []
        for shape_dict in shapes_data:
            if isinstance(shape_dict, dict):
                shape = parse_shape(shape_dict)
                if shape is not None:
                    shapes.append(shape)
        
        if shapes:
            tiles.append(TileData(
                tile_x=tile_x,
                tile_y=tile_y,
                level=level,
                shapes=shapes,
                source_path=bin_path,
            ))
    
    return tiles


def load_level_info(
    root: Path,
    dataset: str,
    run_id: str,
    level: int,
) -> Optional[LevelInfo]:
    """Load level info including grid dimensions and all tiles."""
    tiles = load_tiles_for_level(root, dataset, run_id, level)
    if not tiles:
        return None
    
    # Compute grid dimensions
    nx = max(t.tile_x for t in tiles) + 1
    ny = max(t.tile_y for t in tiles) + 1
    
    return LevelInfo(level=level, nx=nx, ny=ny, tiles=tiles)


def load_dataset_info(
    root: Path,
    dataset: str,
    run_id: str,
) -> Optional[DatasetInfo]:
    """Load complete dataset information."""
    levels_list = discover_levels(root, dataset, run_id)
    if not levels_list:
        return None
    
    levels: Dict[int, LevelInfo] = {}
    for level in levels_list:
        level_info = load_level_info(root, dataset, run_id, level)
        if level_info:
            levels[level] = level_info
    
    if not levels:
        return None
    
    return DatasetInfo(name=dataset, run_id=run_id, levels=levels)


# -----------------------------------------------------------------------------
# Coordinate mapping
# -----------------------------------------------------------------------------

def infer_coord_extents(shapes: Sequence[Shape]) -> Tuple[float, float, float, float]:
    """Infer coordinate extents from shapes (for pixel mode)."""
    if not shapes:
        return 0.0, 0.0, 1.0, 1.0
    
    min_x = float('inf')
    min_y = float('inf')
    max_x = float('-inf')
    max_y = float('-inf')
    
    for shape in shapes:
        cx, cy = shape.center
        r = shape.radius
        min_x = min(min_x, cx - r)
        min_y = min(min_y, cy - r)
        max_x = max(max_x, cx + r)
        max_y = max(max_y, cy + r)
    
    # Avoid zero-size extents
    if max_x <= min_x:
        max_x = min_x + 1.0
    if max_y <= min_y:
        max_y = min_y + 1.0
    
    return min_x, min_y, max_x, max_y


def map_to_world_coords(
    shape: Shape,
    tile_x: int,
    tile_y: int,
    nx: int,
    ny: int,
    coord_mode: str = CoordMode.AUTO,
    extents: Optional[Tuple[float, float, float, float]] = None,
) -> Tuple[float, float, float]:
    """Map tile-local coordinates to world coordinates.
    
    Returns (world_x, world_y, world_r).
    """
    cx, cy = shape.center
    r = shape.radius
    
    if coord_mode == CoordMode.NORMALIZED or coord_mode == CoordMode.AUTO:
        # Assume center is 0..1 within tile
        cx_norm = min(1.0, max(0.0, cx))
        cy_norm = min(1.0, max(0.0, cy))
        r_norm = min(1.0, max(0.0, r))
    elif coord_mode == CoordMode.PIXEL and extents:
        min_x, min_y, max_x, max_y = extents
        width = max_x - min_x
        height = max_y - min_y
        cx_norm = (cx - min_x) / width if width > 0 else 0.5
        cy_norm = (cy - min_y) / height if height > 0 else 0.5
        r_norm = r / max(width, height) if max(width, height) > 0 else 0.1
    else:
        cx_norm = min(1.0, max(0.0, cx))
        cy_norm = min(1.0, max(0.0, cy))
        r_norm = min(1.0, max(0.0, r))
    
    # Map to world coordinates
    world_x = (tile_x + cx_norm) / nx
    world_y = (tile_y + cy_norm) / ny
    world_r = r_norm / max(nx, ny)
    
    return world_x, world_y, world_r


# -----------------------------------------------------------------------------
# Deterministic sorting
# -----------------------------------------------------------------------------

def sort_shapes_deterministic(shapes: List[Shape]) -> List[Shape]:
    """Sort shapes deterministically for stable rendering.
    
    Priority: by id if present, else by stable hash, then by center and radius.
    """
    def sort_key(shape: Shape) -> Tuple[int, str, float, float, float]:
        if shape.id is not None:
            # Shapes with id sort first, by id
            return (0, shape.id, shape.center[0], shape.center[1], shape.radius)
        else:
            # Shapes without id sort by hash, then by geometry
            return (1, shape.stable_hash(), shape.center[0], shape.center[1], shape.radius)
    
    return sorted(shapes, key=sort_key)


# -----------------------------------------------------------------------------
# Color utilities
# -----------------------------------------------------------------------------

def parse_color(fill: Optional[str], default: Tuple[int, int, int] = (128, 128, 128)) -> Tuple[int, int, int]:
    """Parse a color string to RGB tuple."""
    if fill is None:
        return default
    
    fill = fill.strip().lower()
    
    # Named colors
    color_map = {
        "red": (255, 0, 0),
        "green": (0, 255, 0),
        "blue": (0, 0, 255),
        "yellow": (255, 255, 0),
        "cyan": (0, 255, 255),
        "magenta": (255, 0, 255),
        "white": (255, 255, 255),
        "black": (0, 0, 0),
        "gray": (128, 128, 128),
        "grey": (128, 128, 128),
        "orange": (255, 165, 0),
        "purple": (128, 0, 128),
        "pink": (255, 192, 203),
    }
    
    if fill in color_map:
        return color_map[fill]
    
    # Hex color
    if fill.startswith('#'):
        fill = fill[1:]
        if len(fill) == 3:
            fill = ''.join(c * 2 for c in fill)
        if len(fill) == 6:
            try:
                r = int(fill[0:2], 16)
                g = int(fill[2:4], 16)
                b = int(fill[4:6], 16)
                return (r, g, b)
            except ValueError:
                pass
    
    # rgb() notation
    if fill.startswith('rgb(') and fill.endswith(')'):
        try:
            parts = fill[4:-1].split(',')
            if len(parts) == 3:
                r = int(parts[0].strip())
                g = int(parts[1].strip())
                b = int(parts[2].strip())
                return (min(255, max(0, r)), min(255, max(0, g)), min(255, max(0, b)))
        except ValueError:
            pass
    
    return default


def deterministic_color(shape: Shape, index: int) -> Tuple[int, int, int]:
    """Generate a deterministic color for a shape without explicit fill."""
    # Use hash of shape for consistent coloring
    h = hashlib.md5(shape.stable_hash().encode()).digest()
    r = h[0]
    g = h[1]
    b = h[2]
    # Ensure not too dark
    if r + g + b < 128:
        r = min(255, r + 64)
        g = min(255, g + 64)
        b = min(255, b + 64)
    return (r, g, b)


# -----------------------------------------------------------------------------
# Rendering
# -----------------------------------------------------------------------------

class RenderMode:
    DEFAULT = "default"
    WEIGHT = "weight"
    UNCERTAINTY = "uncertainty"
    VECTORS = "vectors"


def render_level(
    level_info: LevelInfo,
    canvas_size: int = 1024,
    coord_mode: str = CoordMode.AUTO,
    render_mode: str = RenderMode.DEFAULT,
    background: Tuple[int, int, int, int] = (0, 0, 0, 255),
) -> Image.Image:
    """Render a stitched PNG for one level.
    
    Returns an RGBA PIL Image.
    """
    # Collect all shapes with world coordinates
    all_shapes: List[Tuple[Shape, float, float, float, TileData]] = []
    
    # For pixel mode, first collect extents
    if coord_mode == CoordMode.PIXEL:
        all_tile_shapes = []
        for tile in level_info.tiles:
            for shape in tile.shapes:
                all_tile_shapes.append(shape)
        extents = infer_coord_extents(all_tile_shapes)
    else:
        extents = None
    
    for tile in level_info.tiles:
        for shape in tile.shapes:
            world_x, world_y, world_r = map_to_world_coords(
                shape,
                tile.tile_x,
                tile.tile_y,
                level_info.nx,
                level_info.ny,
                coord_mode=coord_mode,
                extents=extents,
            )
            all_shapes.append((shape, world_x, world_y, world_r, tile))
    
    # Sort shapes deterministically
    all_shapes.sort(key=lambda x: (
        0 if x[0].id is not None else 1,
        x[0].id if x[0].id is not None else x[0].stable_hash(),
        x[1], x[2], x[3]
    ))
    
    # Create canvas
    img = Image.new('RGBA', (canvas_size, canvas_size), background)
    draw = ImageDraw.Draw(img, 'RGBA')
    
    # Render each shape
    for idx, (shape, world_x, world_y, world_r, tile) in enumerate(all_shapes):
        _render_shape(
            draw,
            shape,
            world_x,
            world_y,
            world_r,
            canvas_size,
            render_mode,
            idx,
        )
    
    return img


def _render_shape(
    draw: ImageDraw.Draw,
    shape: Shape,
    world_x: float,
    world_y: float,
    world_r: float,
    canvas_size: int,
    render_mode: str,
    index: int,
) -> None:
    """Render a single shape onto the canvas."""
    # Convert world coordinates to pixel coordinates
    px = int(world_x * canvas_size)
    py = int(world_y * canvas_size)
    pr = max(1, int(world_r * canvas_size))
    
    # Determine color and alpha based on render mode
    if render_mode == RenderMode.DEFAULT:
        if shape.fill:
            rgb = parse_color(shape.fill)
        else:
            rgb = deterministic_color(shape, index)
        alpha = int(min(255, max(0, shape.alpha * 255)))
    elif render_mode == RenderMode.WEIGHT:
        # Intensity/alpha from weight
        intensity = min(1.0, max(0.0, shape.weight))
        rgb = (255, 255, 255)
        alpha = int(intensity * 255)
    elif render_mode == RenderMode.UNCERTAINTY:
        # Visualize uncertainty via alpha and outline
        rgb = parse_color(shape.fill) if shape.fill else (255, 0, 0)
        # Lower uncertainty = more opaque
        alpha = int((1.0 - min(1.0, shape.uncertainty)) * 255 * shape.alpha)
    elif render_mode == RenderMode.VECTORS:
        # Draw arrows if directional data exists
        direction = shape.extra.get('direction')
        if direction is not None and isinstance(direction, (list, tuple)) and len(direction) >= 2:
            # Draw as arrow
            rgb = parse_color(shape.fill) if shape.fill else deterministic_color(shape, index)
            alpha = int(min(255, max(0, shape.alpha * 255)))
            dx, dy = float(direction[0]), float(direction[1])
            magnitude = math.sqrt(dx * dx + dy * dy)
            if magnitude > 0:
                # Normalize and scale
                dx = dx / magnitude * pr * 2
                dy = dy / magnitude * pr * 2
                end_x = px + int(dx)
                end_y = py + int(dy)
                color = rgb + (alpha,)
                draw.line([(px, py), (end_x, end_y)], fill=color, width=max(1, pr // 4))
                # Arrow head
                head_size = max(3, pr // 2)
                angle = math.atan2(dy, dx)
                left_angle = angle + math.pi * 0.75
                right_angle = angle - math.pi * 0.75
                left_x = end_x + int(head_size * math.cos(left_angle))
                left_y = end_y + int(head_size * math.sin(left_angle))
                right_x = end_x + int(head_size * math.cos(right_angle))
                right_y = end_y + int(head_size * math.sin(right_angle))
                draw.polygon([(end_x, end_y), (left_x, left_y), (right_x, right_y)], fill=color)
            return
        else:
            # No directional data, skip or render as default
            rgb = parse_color(shape.fill) if shape.fill else deterministic_color(shape, index)
            alpha = int(min(255, max(0, shape.alpha * 255)))
    else:
        rgb = parse_color(shape.fill) if shape.fill else deterministic_color(shape, index)
        alpha = int(min(255, max(0, shape.alpha * 255)))
    
    color = rgb + (alpha,)
    
    # Render based on kind
    kind = shape.kind.lower()
    if kind == "circle":
        bbox = [px - pr, py - pr, px + pr, py + pr]
        draw.ellipse(bbox, fill=color)
        if render_mode == RenderMode.UNCERTAINTY and shape.uncertainty > 0:
            # Draw outline to indicate uncertainty
            outline_alpha = int(min(255, shape.uncertainty * 255))
            outline_color = (255, 255, 0, outline_alpha)
            draw.ellipse(bbox, outline=outline_color, width=max(1, pr // 4))
    elif kind == "rect" or kind == "rectangle":
        bbox = [px - pr, py - pr, px + pr, py + pr]
        draw.rectangle(bbox, fill=color)
    elif kind == "line":
        # Use extra data for line endpoints if available
        points = shape.extra.get('points', [])
        if len(points) >= 2:
            start = (int(points[0][0] * canvas_size), int(points[0][1] * canvas_size))
            end = (int(points[1][0] * canvas_size), int(points[1][1] * canvas_size))
            draw.line([start, end], fill=color, width=max(1, pr // 2))
        else:
            # Fallback: draw as small circle
            draw.ellipse([px - 2, py - 2, px + 2, py + 2], fill=color)
    else:
        # Unknown kind - render as circle with warning logged once
        draw.ellipse([px - pr, py - pr, px + pr, py + pr], fill=color)


def render_all_levels(
    root: Path,
    output_dir: Path,
    dataset: str,
    run_id: str,
    canvas_size: int = 1024,
    coord_mode: str = CoordMode.AUTO,
    render_mode: str = RenderMode.DEFAULT,
) -> List[Path]:
    """Render all levels for a dataset/run_id and save as PNGs."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    dataset_info = load_dataset_info(root, dataset, run_id)
    if dataset_info is None:
        logger.warning("No data found for %s/%s", dataset, run_id)
        return []
    
    output_paths: List[Path] = []
    for level, level_info in sorted(dataset_info.levels.items()):
        img = render_level(
            level_info,
            canvas_size=canvas_size,
            coord_mode=coord_mode,
            render_mode=render_mode,
        )
        output_path = output_dir / f"{dataset}_{run_id}_L{level}.png"
        img.save(output_path, 'PNG')
        output_paths.append(output_path)
        logger.info("Rendered %s", output_path)
    
    return output_paths


# -----------------------------------------------------------------------------
# Metrics computation
# -----------------------------------------------------------------------------

def compute_metrics(
    level_info: LevelInfo,
    dataset: str,
    run_id: str,
    canvas_size: int = 1024,
    coord_mode: str = CoordMode.AUTO,
) -> Metrics:
    """Compute metrics for a level."""
    # Collect all shapes with world coordinates
    all_shapes: List[Tuple[Shape, float, float, float]] = []
    
    # For pixel mode extents
    if coord_mode == CoordMode.PIXEL:
        all_tile_shapes = []
        for tile in level_info.tiles:
            for shape in tile.shapes:
                all_tile_shapes.append(shape)
        extents = infer_coord_extents(all_tile_shapes)
    else:
        extents = None
    
    for tile in level_info.tiles:
        for shape in tile.shapes:
            world_x, world_y, world_r = map_to_world_coords(
                shape,
                tile.tile_x,
                tile.tile_y,
                level_info.nx,
                level_info.ny,
                coord_mode=coord_mode,
                extents=extents,
            )
            all_shapes.append((shape, world_x, world_y, world_r))
    
    shape_count = len(all_shapes)
    
    if shape_count == 0:
        return Metrics(
            dataset=dataset,
            run_id=run_id,
            level=level_info.level,
            shape_count=0,
            total_mass=0.0,
            coverage=0.0,
            center_of_mass=(0.5, 0.5),
            spread=0.0,
        )
    
    # Total mass (sum of weights or alphas)
    total_mass = sum(s.weight * s.alpha for s, _, _, _ in all_shapes)
    
    # Center of mass (weighted average)
    if total_mass > 0:
        com_x = sum(wx * s.weight * s.alpha for s, wx, wy, wr in all_shapes) / total_mass
        com_y = sum(wy * s.weight * s.alpha for s, wx, wy, wr in all_shapes) / total_mass
    else:
        com_x = 0.5
        com_y = 0.5
    
    # Spread (second moment / standard deviation from center of mass)
    if total_mass > 0:
        variance = sum(
            ((wx - com_x) ** 2 + (wy - com_y) ** 2) * s.weight * s.alpha
            for s, wx, wy, wr in all_shapes
        ) / total_mass
        spread = math.sqrt(variance)
    else:
        spread = 0.0
    
    # Coverage (approximate - render to compute)
    # Create a simple coverage bitmap
    coverage_size = 256  # Smaller for efficiency
    coverage_array = np.zeros((coverage_size, coverage_size), dtype=np.uint8)
    
    for shape, world_x, world_y, world_r in all_shapes:
        px = int(world_x * coverage_size)
        py = int(world_y * coverage_size)
        pr = max(1, int(world_r * coverage_size))
        
        # Mark pixels as covered
        for dx in range(-pr, pr + 1):
            for dy in range(-pr, pr + 1):
                if dx * dx + dy * dy <= pr * pr:
                    nx = px + dx
                    ny = py + dy
                    if 0 <= nx < coverage_size and 0 <= ny < coverage_size:
                        coverage_array[ny, nx] = 1
    
    coverage = float(np.sum(coverage_array)) / (coverage_size * coverage_size)
    
    return Metrics(
        dataset=dataset,
        run_id=run_id,
        level=level_info.level,
        shape_count=shape_count,
        total_mass=total_mass,
        coverage=coverage,
        center_of_mass=(com_x, com_y),
        spread=spread,
    )


def compute_all_metrics(
    root: Path,
    dataset: str,
    run_id: str,
    coord_mode: str = CoordMode.AUTO,
) -> List[Metrics]:
    """Compute metrics for all levels in a dataset/run_id."""
    dataset_info = load_dataset_info(root, dataset, run_id)
    if dataset_info is None:
        return []
    
    metrics_list: List[Metrics] = []
    for level, level_info in sorted(dataset_info.levels.items()):
        metrics = compute_metrics(level_info, dataset, run_id, coord_mode=coord_mode)
        metrics_list.append(metrics)
    
    return metrics_list


def save_metrics_json(metrics_list: List[Metrics], output_path: Path) -> None:
    """Save metrics to JSON file."""
    data = [
        {
            "dataset": m.dataset,
            "run_id": m.run_id,
            "level": m.level,
            "shape_count": m.shape_count,
            "total_mass": m.total_mass,
            "coverage": m.coverage,
            "center_of_mass": list(m.center_of_mass),
            "spread": m.spread,
        }
        for m in metrics_list
    ]
    output_path.write_text(json.dumps(data, indent=2))


def save_metrics_csv(metrics_list: List[Metrics], output_path: Path) -> None:
    """Save metrics to CSV file."""
    with output_path.open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            "dataset", "run_id", "level", "shape_count", "total_mass",
            "coverage", "center_of_mass_x", "center_of_mass_y", "spread"
        ])
        for m in metrics_list:
            writer.writerow([
                m.dataset, m.run_id, m.level, m.shape_count, m.total_mass,
                m.coverage, m.center_of_mass[0], m.center_of_mass[1], m.spread
            ])


# -----------------------------------------------------------------------------
# Diff support
# -----------------------------------------------------------------------------

def compute_diff(
    root_a: Path,
    root_b: Path,
    dataset: str,
    run_id: str,
    output_dir: Path,
    canvas_size: int = 1024,
    coord_mode: str = CoordMode.AUTO,
    align_pixels: bool = False,
) -> List[Path]:
    """Compare two directory roots and produce delta heatmaps.
    
    If align_pixels is True, use cross-correlation for integer-pixel alignment.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    info_a = load_dataset_info(root_a, dataset, run_id)
    info_b = load_dataset_info(root_b, dataset, run_id)
    
    if info_a is None or info_b is None:
        logger.warning("Missing dataset info for diff: A=%s, B=%s", info_a, info_b)
        return []
    
    # Find common levels
    common_levels = set(info_a.levels.keys()) & set(info_b.levels.keys())
    if not common_levels:
        logger.warning("No common levels between A and B")
        return []
    
    output_paths: List[Path] = []
    
    for level in sorted(common_levels):
        # Render both
        img_a = render_level(info_a.levels[level], canvas_size, coord_mode)
        img_b = render_level(info_b.levels[level], canvas_size, coord_mode)
        
        # Convert to numpy arrays
        arr_a = np.array(img_a).astype(np.float32)
        arr_b = np.array(img_b).astype(np.float32)
        
        # Optional pixel alignment via cross-correlation
        if align_pixels:
            shift = _find_alignment_shift(arr_a, arr_b)
            if shift != (0, 0):
                arr_b = np.roll(arr_b, shift[0], axis=0)
                arr_b = np.roll(arr_b, shift[1], axis=1)
                logger.info("Applied alignment shift: %s for level %d", shift, level)
        
        # Compute difference (absolute difference per channel)
        diff = np.abs(arr_a - arr_b)
        
        # Create heatmap (sum of absolute differences across channels)
        heatmap = np.sum(diff[:, :, :3], axis=2)  # Ignore alpha
        
        # Normalize to 0-255
        max_val = heatmap.max()
        if max_val > 0:
            heatmap = (heatmap / max_val * 255).astype(np.uint8)
        else:
            heatmap = heatmap.astype(np.uint8)
        
        # Create colored heatmap (blue = low, red = high)
        heatmap_colored = np.zeros((canvas_size, canvas_size, 3), dtype=np.uint8)
        heatmap_colored[:, :, 0] = heatmap  # Red channel
        heatmap_colored[:, :, 2] = 255 - heatmap  # Blue channel
        
        # Save
        output_path = output_dir / f"{dataset}_{run_id}_L{level}_diff.png"
        Image.fromarray(heatmap_colored).save(output_path, 'PNG')
        output_paths.append(output_path)
        logger.info("Saved diff heatmap: %s", output_path)
        
        # Also save side-by-side comparison
        comparison = Image.new('RGB', (canvas_size * 3, canvas_size))
        comparison.paste(img_a.convert('RGB'), (0, 0))
        comparison.paste(img_b.convert('RGB'), (canvas_size, 0))
        comparison.paste(Image.fromarray(heatmap_colored), (canvas_size * 2, 0))
        
        comparison_path = output_dir / f"{dataset}_{run_id}_L{level}_comparison.png"
        comparison.save(comparison_path, 'PNG')
        output_paths.append(comparison_path)
    
    return output_paths


def _find_alignment_shift(arr_a: np.ndarray, arr_b: np.ndarray) -> Tuple[int, int]:
    """Find optimal integer-pixel shift to align arr_b to arr_a using cross-correlation."""
    # Use grayscale for correlation
    gray_a = np.mean(arr_a[:, :, :3], axis=2)
    gray_b = np.mean(arr_b[:, :, :3], axis=2)
    
    # FFT-based cross-correlation
    from numpy.fft import fft2, ifft2
    
    f_a = fft2(gray_a)
    f_b = fft2(gray_b)
    
    # Cross power spectrum
    cross = f_a * np.conj(f_b)
    cross_power = ifft2(cross).real
    
    # Find peak
    max_idx = np.unravel_index(np.argmax(cross_power), cross_power.shape)
    
    # Convert to shift (handle wrap-around)
    shift_y = max_idx[0]
    shift_x = max_idx[1]
    
    h, w = gray_a.shape
    if shift_y > h // 2:
        shift_y -= h
    if shift_x > w // 2:
        shift_x -= w
    
    # Only return significant shifts
    if abs(shift_y) < 3 and abs(shift_x) < 3:
        return (0, 0)
    
    return (int(shift_y), int(shift_x))


# -----------------------------------------------------------------------------
# Multi-resolution consistency checks
# -----------------------------------------------------------------------------

def downsample_level(
    level_info: LevelInfo,
    target_nx: int,
    target_ny: int,
    coord_mode: str = CoordMode.AUTO,
) -> np.ndarray:
    """Downsample a level to match a coarser level's grid dimensions."""
    # Render at higher resolution then downsample
    render_size = max(target_nx, target_ny) * 64  # Fine enough for good quality
    img = render_level(level_info, canvas_size=render_size, coord_mode=coord_mode)
    arr = np.array(img).astype(np.float32)
    
    # Resize to target dimensions
    target_size = max(target_nx, target_ny) * 16
    img_resized = img.resize((target_size, target_size), Image.Resampling.LANCZOS)
    
    return np.array(img_resized).astype(np.float32)


def compute_mse(arr_a: np.ndarray, arr_b: np.ndarray) -> float:
    """Compute Mean Squared Error between two arrays."""
    if arr_a.shape != arr_b.shape:
        # Resize if needed
        min_h = min(arr_a.shape[0], arr_b.shape[0])
        min_w = min(arr_a.shape[1], arr_b.shape[1])
        arr_a = arr_a[:min_h, :min_w]
        arr_b = arr_b[:min_h, :min_w]
    
    return float(np.mean((arr_a - arr_b) ** 2))


def compute_ssim(arr_a: np.ndarray, arr_b: np.ndarray) -> Optional[float]:
    """Compute SSIM if available, otherwise return None."""
    try:
        from skimage.metrics import structural_similarity as ssim
        
        if arr_a.shape != arr_b.shape:
            min_h = min(arr_a.shape[0], arr_b.shape[0])
            min_w = min(arr_a.shape[1], arr_b.shape[1])
            arr_a = arr_a[:min_h, :min_w]
            arr_b = arr_b[:min_h, :min_w]
        
        # Convert to grayscale for SSIM
        if len(arr_a.shape) == 3:
            gray_a = np.mean(arr_a[:, :, :3], axis=2)
            gray_b = np.mean(arr_b[:, :, :3], axis=2)
        else:
            gray_a = arr_a
            gray_b = arr_b
        
        return float(ssim(gray_a, gray_b, data_range=255))
    except ImportError:
        return None


def check_multiresolution_consistency(
    root: Path,
    dataset: str,
    run_id: str,
    output_dir: Path,
    coord_mode: str = CoordMode.AUTO,
) -> Dict[str, Any]:
    """Check multi-resolution consistency by comparing adjacent levels.
    
    Downsample fine level to predict coarser level, then compare.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    dataset_info = load_dataset_info(root, dataset, run_id)
    if dataset_info is None:
        return {"error": "Dataset not found"}
    
    levels = sorted(dataset_info.levels.keys())
    if len(levels) < 2:
        return {"error": "Need at least 2 levels for consistency check"}
    
    results: Dict[str, Any] = {
        "dataset": dataset,
        "run_id": run_id,
        "level_comparisons": [],
    }
    
    for i in range(len(levels) - 1):
        fine_level = levels[i]
        coarse_level = levels[i + 1]
        
        fine_info = dataset_info.levels[fine_level]
        coarse_info = dataset_info.levels[coarse_level]
        
        # Render both at same resolution for comparison
        render_size = 512
        img_fine = render_level(fine_info, canvas_size=render_size, coord_mode=coord_mode)
        img_coarse = render_level(coarse_info, canvas_size=render_size, coord_mode=coord_mode)
        
        # Downsample fine to coarse resolution
        fine_downsampled = img_fine.resize(
            (render_size // 2, render_size // 2), 
            Image.Resampling.LANCZOS
        ).resize((render_size, render_size), Image.Resampling.LANCZOS)
        
        arr_fine_ds = np.array(fine_downsampled).astype(np.float32)
        arr_coarse = np.array(img_coarse).astype(np.float32)
        
        mse = compute_mse(arr_fine_ds, arr_coarse)
        ssim_val = compute_ssim(arr_fine_ds, arr_coarse)
        
        comparison = {
            "fine_level": fine_level,
            "coarse_level": coarse_level,
            "mse": mse,
            "ssim": ssim_val,
        }
        results["level_comparisons"].append(comparison)
        
        # Generate disagreement map
        diff = np.abs(arr_fine_ds - arr_coarse)
        heatmap = np.sum(diff[:, :, :3], axis=2)
        max_val = heatmap.max()
        if max_val > 0:
            heatmap = (heatmap / max_val * 255).astype(np.uint8)
        else:
            heatmap = heatmap.astype(np.uint8)
        
        # Save disagreement map
        disagreement_path = output_dir / f"{dataset}_{run_id}_L{fine_level}_L{coarse_level}_disagreement.png"
        Image.fromarray(heatmap).save(disagreement_path, 'PNG')
        logger.info("Saved disagreement map: %s", disagreement_path)
    
    # Save JSON report
    report_path = output_dir / f"{dataset}_{run_id}_consistency_report.json"
    report_path.write_text(json.dumps(results, indent=2))
    logger.info("Saved consistency report: %s", report_path)
    
    return results


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="HIM Tile Processor - Directory-based tile processing, rendering, and analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List available datasets and runs
  python -m him.cli.tile_processor --root ./data list

  # Render all levels for a dataset/run
  python -m him.cli.tile_processor --root ./data render episodic_vector run_001 --output ./output

  # Compute metrics
  python -m him.cli.tile_processor --root ./data metrics episodic_vector run_001 --output ./metrics

  # Compare two directories
  python -m him.cli.tile_processor diff ./data_a ./data_b episodic_vector run_001 --output ./diff

  # Check multi-resolution consistency
  python -m him.cli.tile_processor --root ./data consistency episodic_vector run_001 --output ./consistency
""",
    )
    
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Root directory containing tile data",
    )
    parser.add_argument(
        "--log-level",
        default="info",
        choices=["debug", "info", "warning", "error"],
        help="Logging level",
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List available datasets and runs")
    
    # Render command
    render_parser = subparsers.add_parser("render", help="Render tiles to PNG")
    render_parser.add_argument("dataset", help="Dataset name (e.g., episodic_vector)")
    render_parser.add_argument("run_id", help="Run ID")
    render_parser.add_argument("--output", type=Path, required=True, help="Output directory")
    render_parser.add_argument("--canvas-size", type=int, default=1024, help="Canvas size in pixels")
    render_parser.add_argument(
        "--coord-mode",
        choices=[CoordMode.AUTO, CoordMode.NORMALIZED, CoordMode.PIXEL],
        default=CoordMode.AUTO,
        help="Coordinate mapping mode",
    )
    render_parser.add_argument(
        "--render-mode",
        choices=[RenderMode.DEFAULT, RenderMode.WEIGHT, RenderMode.UNCERTAINTY, RenderMode.VECTORS],
        default=RenderMode.DEFAULT,
        help="Render mode",
    )
    
    # Metrics command
    metrics_parser = subparsers.add_parser("metrics", help="Compute metrics")
    metrics_parser.add_argument("dataset", help="Dataset name")
    metrics_parser.add_argument("run_id", help="Run ID")
    metrics_parser.add_argument("--output", type=Path, required=True, help="Output directory")
    metrics_parser.add_argument(
        "--coord-mode",
        choices=[CoordMode.AUTO, CoordMode.NORMALIZED, CoordMode.PIXEL],
        default=CoordMode.AUTO,
        help="Coordinate mapping mode",
    )
    
    # Diff command
    diff_parser = subparsers.add_parser("diff", help="Compare two directory roots")
    diff_parser.add_argument("root_a", type=Path, help="First root directory")
    diff_parser.add_argument("root_b", type=Path, help="Second root directory")
    diff_parser.add_argument("dataset", help="Dataset name")
    diff_parser.add_argument("run_id", help="Run ID")
    diff_parser.add_argument("--output", type=Path, required=True, help="Output directory")
    diff_parser.add_argument("--canvas-size", type=int, default=1024, help="Canvas size")
    diff_parser.add_argument(
        "--coord-mode",
        choices=[CoordMode.AUTO, CoordMode.NORMALIZED, CoordMode.PIXEL],
        default=CoordMode.AUTO,
        help="Coordinate mapping mode",
    )
    diff_parser.add_argument(
        "--align",
        action="store_true",
        help="Use cross-correlation for integer-pixel alignment",
    )
    
    # Consistency command
    consistency_parser = subparsers.add_parser(
        "consistency",
        help="Check multi-resolution consistency",
    )
    consistency_parser.add_argument("dataset", help="Dataset name")
    consistency_parser.add_argument("run_id", help="Run ID")
    consistency_parser.add_argument("--output", type=Path, required=True, help="Output directory")
    consistency_parser.add_argument(
        "--coord-mode",
        choices=[CoordMode.AUTO, CoordMode.NORMALIZED, CoordMode.PIXEL],
        default=CoordMode.AUTO,
        help="Coordinate mapping mode",
    )
    
    # Render all command
    render_all_parser = subparsers.add_parser("render-all", help="Render all datasets and runs")
    render_all_parser.add_argument("--output", type=Path, required=True, help="Output directory")
    render_all_parser.add_argument("--canvas-size", type=int, default=1024, help="Canvas size")
    render_all_parser.add_argument(
        "--coord-mode",
        choices=[CoordMode.AUTO, CoordMode.NORMALIZED, CoordMode.PIXEL],
        default=CoordMode.AUTO,
        help="Coordinate mapping mode",
    )
    render_all_parser.add_argument(
        "--render-mode",
        choices=[RenderMode.DEFAULT, RenderMode.WEIGHT, RenderMode.UNCERTAINTY, RenderMode.VECTORS],
        default=RenderMode.DEFAULT,
        help="Render mode",
    )
    
    args = parser.parse_args(argv)
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    
    if args.command is None:
        parser.print_help()
        return 1
    
    if args.command == "list":
        root = args.root
        datasets = discover_datasets(root)
        if not datasets:
            print(f"No datasets found in {root}")
            return 0
        
        for dataset in datasets:
            print(f"\nDataset: {dataset}")
            run_ids = discover_run_ids(root, dataset)
            for run_id in run_ids:
                levels = discover_levels(root, dataset, run_id)
                print(f"  Run: {run_id}, Levels: {levels}")
        
        return 0
    
    elif args.command == "render":
        output_paths = render_all_levels(
            args.root,
            args.output,
            args.dataset,
            args.run_id,
            canvas_size=args.canvas_size,
            coord_mode=args.coord_mode,
            render_mode=args.render_mode,
        )
        print(f"Rendered {len(output_paths)} images")
        for p in output_paths:
            print(f"  {p}")
        return 0
    
    elif args.command == "metrics":
        metrics_list = compute_all_metrics(
            args.root,
            args.dataset,
            args.run_id,
            coord_mode=args.coord_mode,
        )
        if not metrics_list:
            print("No metrics computed (no data found)")
            return 1
        
        args.output.mkdir(parents=True, exist_ok=True)
        json_path = args.output / f"{args.dataset}_{args.run_id}_metrics.json"
        csv_path = args.output / f"{args.dataset}_{args.run_id}_metrics.csv"
        
        save_metrics_json(metrics_list, json_path)
        save_metrics_csv(metrics_list, csv_path)
        
        print(f"Saved metrics to:")
        print(f"  {json_path}")
        print(f"  {csv_path}")
        
        # Print summary
        print("\nMetrics summary:")
        for m in metrics_list:
            print(f"  Level {m.level}: {m.shape_count} shapes, mass={m.total_mass:.2f}, "
                  f"coverage={m.coverage:.2%}, spread={m.spread:.4f}")
        
        return 0
    
    elif args.command == "diff":
        output_paths = compute_diff(
            args.root_a,
            args.root_b,
            args.dataset,
            args.run_id,
            args.output,
            canvas_size=args.canvas_size,
            coord_mode=args.coord_mode,
            align_pixels=args.align,
        )
        print(f"Generated {len(output_paths)} diff images")
        for p in output_paths:
            print(f"  {p}")
        return 0
    
    elif args.command == "consistency":
        results = check_multiresolution_consistency(
            args.root,
            args.dataset,
            args.run_id,
            args.output,
            coord_mode=args.coord_mode,
        )
        if "error" in results:
            print(f"Error: {results['error']}")
            return 1
        
        print("Multi-resolution consistency check:")
        for comp in results.get("level_comparisons", []):
            ssim_str = f", SSIM={comp['ssim']:.4f}" if comp.get('ssim') is not None else ""
            print(f"  L{comp['fine_level']} vs L{comp['coarse_level']}: MSE={comp['mse']:.2f}{ssim_str}")
        
        return 0
    
    elif args.command == "render-all":
        root = args.root
        datasets = discover_datasets(root)
        total_rendered = 0
        
        for dataset in datasets:
            run_ids = discover_run_ids(root, dataset)
            for run_id in run_ids:
                output_dir = args.output / dataset / run_id
                output_paths = render_all_levels(
                    root,
                    output_dir,
                    dataset,
                    run_id,
                    canvas_size=args.canvas_size,
                    coord_mode=args.coord_mode,
                    render_mode=args.render_mode,
                )
                total_rendered += len(output_paths)
        
        print(f"Rendered {total_rendered} images total")
        return 0
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
