"""CLI tool for rendering HIM tile data from directory structure."""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CoordMode(str, Enum):
    """Coordinate mapping modes."""

    AUTO = "auto"
    NORMALIZED = "normalized"
    PIXEL = "pixel"


class RenderMode(str, Enum):
    """Rendering modes."""

    DEFAULT = "default"
    WEIGHT = "weight"
    UNCERTAINTY = "uncertainty"
    VECTORS = "vectors"


@dataclass
class Shape:
    """Represents a shape from a tile file."""

    kind: str
    center: Tuple[float, float]
    radius: Optional[float] = None
    fill: Optional[str] = None
    alpha: Optional[float] = None
    weight: Optional[float] = None
    channel: Optional[str] = None
    uncertainty: Optional[float] = None
    id: Optional[str] = None
    points: Optional[List[Tuple[float, float]]] = None

    def stable_hash(self) -> str:
        """Generate stable hash for deterministic sorting."""
        data = json.dumps(
            {
                "kind": self.kind,
                "center": self.center,
                "radius": self.radius,
                "fill": self.fill,
                "alpha": self.alpha,
                "weight": self.weight,
                "channel": self.channel,
                "uncertainty": self.uncertainty,
                "id": self.id,
                "points": self.points,
            },
            sort_keys=True,
        )
        return hashlib.sha256(data.encode()).hexdigest()


@dataclass
class TileData:
    """Represents a single tile with its shapes."""

    dataset: str
    run_id: str
    level: int
    tile_x: int
    tile_y: int
    shapes: List[Shape]
    file_path: Path


@dataclass
class GridInfo:
    """Information about tile grid for a level."""

    nx: int
    ny: int
    min_x: int
    min_y: int
    max_x: int
    max_y: int


class TileReader:
    """Reads tiles from directory structure."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def discover_datasets(self) -> List[str]:
        """Discover available datasets."""
        datasets = []
        for item in self.root.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                datasets.append(item.name)
        return sorted(datasets)

    def discover_run_ids(self, dataset: str) -> List[str]:
        """Discover run IDs for a dataset."""
        dataset_path = self.root / dataset
        if not dataset_path.exists():
            return []
        run_ids = []
        for item in dataset_path.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                run_ids.append(item.name)
        return sorted(run_ids)

    def discover_levels(self, dataset: str, run_id: str) -> List[int]:
        """Discover levels for a dataset/run_id."""
        run_path = self.root / dataset / run_id
        if not run_path.exists():
            return []
        levels = []
        for item in run_path.iterdir():
            if item.is_dir() and item.name.startswith("L"):
                try:
                    level = int(item.name[1:])
                    levels.append(level)
                except ValueError:
                    continue
        return sorted(levels)

    def discover_tiles(self, dataset: str, run_id: str, level: int) -> List[Tuple[int, int]]:
        """Discover tile coordinates for a level."""
        level_path = self.root / dataset / run_id / f"L{level}"
        if not level_path.exists():
            return []
        tiles = []
        for x_dir in level_path.iterdir():
            if x_dir.is_dir() and x_dir.name.startswith("x"):
                try:
                    tile_x = int(x_dir.name[1:])
                    for y_dir in x_dir.iterdir():
                        if y_dir.is_dir() and y_dir.name.startswith("y"):
                            try:
                                tile_y = int(y_dir.name[1:])
                                tiles.append((tile_x, tile_y))
                            except ValueError:
                                continue
                except ValueError:
                    continue
        return sorted(tiles)

    def load_tile(self, dataset: str, run_id: str, level: int, tile_x: int, tile_y: int) -> Optional[TileData]:
        """Load a single tile, returning None if not found or invalid."""
        tile_path = self.root / dataset / run_id / f"L{level}" / f"x{tile_x}" / f"y{tile_y}"
        if not tile_path.exists():
            return None

        shapes = []
        for bin_file in tile_path.glob("*.bin"):
            try:
                content = bin_file.read_text(encoding="utf-8")
                data = json.loads(content)
                tile_shapes = data.get("shapes", [])
                for shape_data in tile_shapes:
                    try:
                        shape = self._parse_shape(shape_data)
                        if shape:
                            shapes.append(shape)
                    except Exception as e:
                        logger.warning(f"Failed to parse shape in {bin_file}: {e}")
                        continue
            except Exception as e:
                logger.warning(f"Failed to load {bin_file}: {e}")
                continue

        return TileData(
            dataset=dataset,
            run_id=run_id,
            level=level,
            tile_x=tile_x,
            tile_y=tile_y,
            shapes=shapes,
            file_path=tile_path,
        )

    def _parse_shape(self, shape_data: dict) -> Optional[Shape]:
        """Parse a shape from JSON data."""
        kind = shape_data.get("kind")
        if not kind:
            return None

        center = shape_data.get("center", [0.0, 0.0])
        if not isinstance(center, list) or len(center) < 2:
            return None

        try:
            radius = shape_data.get("radius")
            if radius is not None:
                radius = float(radius)
        except (ValueError, TypeError):
            radius = None

        try:
            alpha = shape_data.get("alpha")
            if alpha is not None:
                alpha = float(alpha)
        except (ValueError, TypeError):
            alpha = None

        try:
            weight = shape_data.get("weight")
            if weight is not None:
                weight = float(weight)
        except (ValueError, TypeError):
            weight = None

        try:
            uncertainty = shape_data.get("uncertainty")
            if uncertainty is not None:
                uncertainty = float(uncertainty)
        except (ValueError, TypeError):
            uncertainty = None

        return Shape(
            kind=str(kind),
            center=(float(center[0]), float(center[1])),
            radius=radius,
            fill=shape_data.get("fill"),
            alpha=alpha,
            weight=weight,
            channel=shape_data.get("channel"),
            uncertainty=uncertainty,
            id=shape_data.get("id"),
            points=shape_data.get("points"),
        )

    def get_grid_info(self, dataset: str, run_id: str, level: int) -> Optional[GridInfo]:
        """Get grid information for a level."""
        tiles = self.discover_tiles(dataset, run_id, level)
        if not tiles:
            return None
        tile_xs = [t[0] for t in tiles]
        tile_ys = [t[1] for t in tiles]
        return GridInfo(
            nx=max(tile_xs) + 1,
            ny=max(tile_ys) + 1,
            min_x=min(tile_xs),
            min_y=min(tile_ys),
            max_x=max(tile_xs),
            max_y=max(tile_ys),
        )


class CoordinateMapper:
    """Maps tile-local coordinates to world coordinates."""

    def __init__(self, grid_info: GridInfo, coord_mode: CoordMode = CoordMode.AUTO) -> None:
        self.grid_info = grid_info
        self.coord_mode = coord_mode
        self.nx = grid_info.nx
        self.ny = grid_info.ny

    def to_world(self, tile_x: int, tile_y: int, local_cx: float, local_cy: float, local_r: Optional[float] = None) -> Tuple[float, float, Optional[float]]:
        """Convert tile-local coordinates to world coordinates."""
        if self.coord_mode == CoordMode.NORMALIZED:
            world_x = (tile_x + local_cx) / self.nx
            world_y = (tile_y + local_cy) / self.ny
            world_r = local_r / max(self.nx, self.ny) if local_r is not None else None
        elif self.coord_mode == CoordMode.PIXEL:
            world_x = tile_x + local_cx
            world_y = tile_y + local_cy
            world_r = local_r
        else:  # AUTO
            world_x = (tile_x + local_cx) / self.nx
            world_y = (tile_y + local_cy) / self.ny
            world_r = local_r / max(self.nx, self.ny) if local_r is not None else None
        return world_x, world_y, world_r


class Renderer:
    """Renders tiles to stitched PNG images."""

    def __init__(
        self,
        canvas_size: int = 2048,
        render_mode: RenderMode = RenderMode.DEFAULT,
        coord_mode: CoordMode = CoordMode.AUTO,
    ) -> None:
        self.canvas_size = canvas_size
        self.render_mode = render_mode
        self.coord_mode = coord_mode

    def render_level(
        self,
        reader: TileReader,
        dataset: str,
        run_id: str,
        level: int,
        output_path: Path,
    ) -> None:
        """Render a complete level as a stitched PNG."""
        grid_info = reader.get_grid_info(dataset, run_id, level)
        if not grid_info:
            logger.warning(f"No tiles found for {dataset}/{run_id}/L{level}")
            return

        mapper = CoordinateMapper(grid_info, self.coord_mode)
        tiles = reader.discover_tiles(dataset, run_id, level)

        # Collect all shapes with world coordinates
        world_shapes: List[Tuple[Shape, float, float, Optional[float]]] = []
        for tile_x, tile_y in tiles:
            tile_data = reader.load_tile(dataset, run_id, level, tile_x, tile_y)
            if not tile_data:
                continue
            for shape in tile_data.shapes:
                cx, cy = shape.center
                world_x, world_y, world_r = mapper.to_world(tile_x, tile_y, cx, cy, shape.radius)
                world_shapes.append((shape, world_x, world_y, world_r))

        # Deterministic sort: by id if present, else by stable hash, then by position
        world_shapes.sort(key=lambda s: (
            s[0].id if s[0].id is not None else s[0].stable_hash(),
            s[1],  # world_x
            s[2],  # world_y
            s[3] if s[3] is not None else 0.0,  # world_r
        ))

        # Create canvas
        img = Image.new("RGBA", (self.canvas_size, self.canvas_size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Render shapes
        for shape, world_x, world_y, world_r in world_shapes:
            self._render_shape(draw, shape, world_x, world_y, world_r)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path, "PNG")
        logger.info(f"Rendered {len(world_shapes)} shapes to {output_path} (grid: {grid_info.nx}x{grid_info.ny})")

    def _render_shape(
        self,
        draw: ImageDraw.ImageDraw,
        shape: Shape,
        world_x: float,
        world_y: float,
        world_r: Optional[float],
    ) -> None:
        """Render a single shape on the canvas."""
        # Determine color and alpha
        color, alpha = self._get_color_alpha(shape)

        if shape.kind == "circle" and world_r is not None:
            # Convert world coordinates to pixel coordinates
            px = int(world_x * self.canvas_size)
            py = int(world_y * self.canvas_size)
            radius_px = int(world_r * self.canvas_size)
            if radius_px > 0 and 0 <= px < self.canvas_size and 0 <= py < self.canvas_size:
                bbox = [px - radius_px, py - radius_px, px + radius_px, py + radius_px]
                draw.ellipse(bbox, fill=color + (alpha,), outline=None)
        elif shape.points:
            # Render polygon/polyline
            points = [
                (int(p[0] * self.canvas_size), int(p[1] * self.canvas_size))
                for p in shape.points
            ]
            if len(points) >= 2:
                draw.polygon(points, fill=color + (alpha,), outline=None)
        elif shape.kind == "circle" and shape.radius is not None:
            # Fallback: use tile-local radius if world_r not available
            px = int(world_x * self.canvas_size)
            py = int(world_y * self.canvas_size)
            radius_px = int(shape.radius * self.canvas_size)
            if radius_px > 0 and 0 <= px < self.canvas_size and 0 <= py < self.canvas_size:
                bbox = [px - radius_px, py - radius_px, px + radius_px, py + radius_px]
                draw.ellipse(bbox, fill=color + (alpha,), outline=None)

    def _get_color_alpha(self, shape: Shape) -> Tuple[Tuple[int, int, int], int]:
        """Get color and alpha based on render mode."""
        if self.render_mode == RenderMode.WEIGHT:
            weight = shape.weight if shape.weight is not None else 1.0
            alpha = int(min(255, max(0, weight * 255)))
            color = (255, 255, 255) if shape.fill is None else self._parse_color(shape.fill)
            return color, alpha
        elif self.render_mode == RenderMode.UNCERTAINTY:
            uncertainty = shape.uncertainty if shape.uncertainty is not None else 0.0
            alpha = int(min(255, max(0, uncertainty * 255)))
            color = (255, 0, 0)  # Red for uncertainty
            return color, alpha
        else:  # DEFAULT
            color = self._parse_color(shape.fill) if shape.fill else (128, 128, 128)
            alpha = int(min(255, max(0, (shape.alpha if shape.alpha is not None else 1.0) * 255)))
            return color, alpha

    def _parse_color(self, color_str: str) -> Tuple[int, int, int]:
        """Parse color string to RGB tuple."""
        if color_str.startswith("#"):
            hex_color = color_str[1:]
            if len(hex_color) == 6:
                return (
                    int(hex_color[0:2], 16),
                    int(hex_color[2:4], 16),
                    int(hex_color[4:6], 16),
                )
        # Default gray
        return (128, 128, 128)


class MetricsCalculator:
    """Calculates metrics for tile data."""

    @staticmethod
    def calculate_level_metrics(
        reader: TileReader,
        dataset: str,
        run_id: str,
        level: int,
    ) -> dict:
        """Calculate metrics for a level."""
        tiles = reader.discover_tiles(dataset, run_id, level)
        all_shapes = []
        total_mass = 0.0
        total_weight = 0.0

        for tile_x, tile_y in tiles:
            tile_data = reader.load_tile(dataset, run_id, level, tile_x, tile_y)
            if not tile_data:
                continue
            for shape in tile_data.shapes:
                all_shapes.append(shape)
                weight = shape.weight if shape.weight is not None else (shape.alpha if shape.alpha is not None else 1.0)
                total_weight += weight
                if shape.radius:
                    area = math.pi * shape.radius * shape.radius
                    total_mass += area * weight

        # Center of mass
        com_x = 0.0
        com_y = 0.0
        for shape in all_shapes:
            weight = shape.weight if shape.weight is not None else (shape.alpha if shape.alpha is not None else 1.0)
            com_x += shape.center[0] * weight
            com_y += shape.center[1] * weight
        if total_weight > 0:
            com_x /= total_weight
            com_y /= total_weight

        # Second moment / spread
        spread = 0.0
        for shape in all_shapes:
            weight = shape.weight if shape.weight is not None else (shape.alpha if shape.alpha is not None else 1.0)
            dx = shape.center[0] - com_x
            dy = shape.center[1] - com_y
            spread += (dx * dx + dy * dy) * weight
        if total_weight > 0:
            spread /= total_weight

        grid_info = reader.get_grid_info(dataset, run_id, level)
        total_tiles = grid_info.nx * grid_info.ny if grid_info else 1
        coverage = len(all_shapes) / total_tiles if total_tiles > 0 else 0.0

        return {
            "dataset": dataset,
            "run_id": run_id,
            "level": level,
            "shape_count": len(all_shapes),
            "total_mass": total_mass,
            "total_weight": total_weight,
            "coverage": coverage,
            "center_of_mass": [com_x, com_y],
            "spread": spread,
        }


class DiffCalculator:
    """Calculates differences between two directory roots."""

    def __init__(self, root_a: Path, root_b: Path) -> None:
        self.reader_a = TileReader(root_a)
        self.reader_b = TileReader(root_b)

    def diff_level(
        self,
        dataset: str,
        run_id: str,
        level: int,
        output_path: Path,
        canvas_size: int = 2048,
    ) -> dict:
        """Generate diff visualization and metrics for a level."""
        grid_info_a = self.reader_a.get_grid_info(dataset, run_id, level)
        grid_info_b = self.reader_b.get_grid_info(dataset, run_id, level)

        if not grid_info_a or not grid_info_b:
            logger.warning(f"Missing grid info for diff")
            return {}

        # Render both levels
        renderer = Renderer(canvas_size=canvas_size)
        img_a = self._render_to_image(self.reader_a, dataset, run_id, level, grid_info_a, canvas_size)
        img_b = self._render_to_image(self.reader_b, dataset, run_id, level, grid_info_b, canvas_size)

        # Ensure same size
        if img_a.size != img_b.size:
            img_b = img_b.resize(img_a.size, Image.Resampling.LANCZOS)

        # Compute delta
        arr_a = np.array(img_a.convert("L"))
        arr_b = np.array(img_b.convert("L"))
        delta = np.abs(arr_a.astype(float) - arr_b.astype(float))
        delta_img = Image.fromarray(delta.astype(np.uint8), mode="L")

        # Save delta heatmap
        delta_path = output_path.parent / f"{output_path.stem}_delta.png"
        delta_path.parent.mkdir(parents=True, exist_ok=True)
        delta_img.save(delta_path)

        mse = float(np.mean(delta * delta))
        return {
            "mse": mse,
            "mean_delta": float(np.mean(delta)),
            "max_delta": float(np.max(delta)),
        }

    def _render_to_image(
        self,
        reader: TileReader,
        dataset: str,
        run_id: str,
        level: int,
        grid_info: GridInfo,
        canvas_size: int,
    ) -> Image.Image:
        """Render level to PIL Image."""
        mapper = CoordinateMapper(grid_info, CoordMode.AUTO)
        tiles = reader.discover_tiles(dataset, run_id, level)
        img = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        renderer = Renderer(canvas_size=canvas_size)

        for tile_x, tile_y in tiles:
            tile_data = reader.load_tile(dataset, run_id, level, tile_x, tile_y)
            if not tile_data:
                continue
            for shape in tile_data.shapes:
                cx, cy = shape.center
                world_x, world_y, world_r = mapper.to_world(tile_x, tile_y, cx, cy, shape.radius)
                renderer._render_shape(draw, shape, world_x, world_y, world_r)

        return img


class ConsistencyChecker:
    """Checks multi-resolution consistency."""

    @staticmethod
    def check_consistency(
        reader: TileReader,
        dataset: str,
        run_id: str,
        fine_level: int,
        coarse_level: int,
        output_path: Path,
        canvas_size: int = 2048,
    ) -> dict:
        """Check consistency between fine and coarse levels."""
        fine_grid = reader.get_grid_info(dataset, run_id, fine_level)
        coarse_grid = reader.get_grid_info(dataset, run_id, coarse_level)

        if not fine_grid or not coarse_grid:
            return {}

        # Render fine level
        renderer = Renderer(canvas_size=canvas_size)
        fine_img = ConsistencyChecker._render_level_to_image(
            reader, dataset, run_id, fine_level, fine_grid, canvas_size
        )

        # Downsample fine level
        scale_factor = 2 ** (fine_level - coarse_level)
        downsampled = fine_img.resize(
            (canvas_size // scale_factor, canvas_size // scale_factor),
            Image.Resampling.LANCZOS,
        ).resize((canvas_size, canvas_size), Image.Resampling.NEAREST)

        # Render coarse level
        coarse_img = ConsistencyChecker._render_level_to_image(
            reader, dataset, run_id, coarse_level, coarse_grid, canvas_size
        )

        # Ensure same size
        if downsampled.size != coarse_img.size:
            coarse_img = coarse_img.resize(downsampled.size, Image.Resampling.LANCZOS)

        # Compare
        arr_pred = np.array(downsampled.convert("L"))
        arr_actual = np.array(coarse_img.convert("L"))
        delta = np.abs(arr_pred.astype(float) - arr_actual.astype(float))
        mse = float(np.mean(delta * delta))

        # Save disagreement map
        delta_img = Image.fromarray(delta.astype(np.uint8), mode="L")
        delta_path = output_path.parent / f"{output_path.stem}_disagreement.png"
        delta_path.parent.mkdir(parents=True, exist_ok=True)
        delta_img.save(delta_path)

        return {
            "fine_level": fine_level,
            "coarse_level": coarse_level,
            "mse": mse,
            "mean_delta": float(np.mean(delta)),
            "max_delta": float(np.max(delta)),
        }

    @staticmethod
    def _render_level_to_image(
        reader: TileReader,
        dataset: str,
        run_id: str,
        level: int,
        grid_info: GridInfo,
        canvas_size: int,
    ) -> Image.Image:
        """Render level to PIL Image."""
        mapper = CoordinateMapper(grid_info, CoordMode.AUTO)
        tiles = reader.discover_tiles(dataset, run_id, level)
        img = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        renderer = Renderer(canvas_size=canvas_size)

        for tile_x, tile_y in tiles:
            tile_data = reader.load_tile(dataset, run_id, level, tile_x, tile_y)
            if not tile_data:
                continue
            for shape in tile_data.shapes:
                cx, cy = shape.center
                world_x, world_y, world_r = mapper.to_world(tile_x, tile_y, cx, cy, shape.radius)
                renderer._render_shape(draw, shape, world_x, world_y, world_r)

        return img


def main() -> None:
    parser = argparse.ArgumentParser(description="Render HIM tile data from directory structure")
    parser.add_argument("root", help="Root directory containing tile data")
    parser.add_argument("--dataset", help="Dataset name (e.g., episodic_vector)")
    parser.add_argument("--run-id", help="Run ID")
    parser.add_argument("--level", type=int, help="Level to render")
    parser.add_argument("--output", help="Output directory for rendered images")
    parser.add_argument("--render-mode", choices=[m.value for m in RenderMode], default=RenderMode.DEFAULT.value)
    parser.add_argument("--coord-mode", choices=[m.value for m in CoordMode], default=CoordMode.AUTO.value)
    parser.add_argument("--canvas-size", type=int, default=2048, help="Canvas size in pixels")
    parser.add_argument("--metrics", action="store_true", help="Compute and save metrics")
    parser.add_argument("--diff", help="Compare with another root directory")
    parser.add_argument("--consistency", action="store_true", help="Check multi-resolution consistency")

    args = parser.parse_args()

    root = Path(args.root)
    if not root.exists():
        logger.error(f"Root directory does not exist: {root}")
        return

    reader = TileReader(root)
    output_dir = Path(args.output) if args.output else root / "rendered"

    # Discover datasets if not specified
    if args.dataset:
        datasets = [args.dataset]
    else:
        datasets = reader.discover_datasets()
        logger.info(f"Discovered datasets: {datasets}")

    all_metrics = []

    for dataset in datasets:
        # Discover run IDs if not specified
        if args.run_id:
            run_ids = [args.run_id]
        else:
            run_ids = reader.discover_run_ids(dataset)
            logger.info(f"Discovered run IDs for {dataset}: {run_ids}")

        if not run_ids:
            logger.warning(f"No run IDs found for dataset {dataset}")
            continue

        for run_id in run_ids:
            # Discover levels if not specified
            if args.level is not None:
                levels = [args.level]
            else:
                levels = reader.discover_levels(dataset, run_id)
                logger.info(f"Discovered levels for {dataset}/{run_id}: {levels}")

            if not levels:
                logger.warning(f"No levels found for {dataset}/{run_id}")
                continue

            for level in levels:
                # Render level
                renderer = Renderer(
                    canvas_size=args.canvas_size,
                    render_mode=RenderMode(args.render_mode),
                    coord_mode=CoordMode(args.coord_mode),
                )
                output_path = output_dir / dataset / run_id / f"L{level}_render.png"
                try:
                    renderer.render_level(reader, dataset, run_id, level, output_path)
                except Exception as e:
                    logger.error(f"Failed to render {dataset}/{run_id}/L{level}: {e}")
                    continue

                # Compute metrics
                if args.metrics:
                    try:
                        calc = MetricsCalculator()
                        metrics = calc.calculate_level_metrics(reader, dataset, run_id, level)
                        all_metrics.append(metrics)
                    except Exception as e:
                        logger.error(f"Failed to compute metrics for {dataset}/{run_id}/L{level}: {e}")
                        continue

                # Diff if requested
                if args.diff:
                    try:
                        diff_calc = DiffCalculator(root, Path(args.diff))
                        diff_output = output_dir / dataset / run_id / f"L{level}_diff.png"
                        diff_result = diff_calc.diff_level(dataset, run_id, level, diff_output, args.canvas_size)
                        logger.info(f"Diff result for {dataset}/{run_id}/L{level}: {diff_result}")
                    except Exception as e:
                        logger.error(f"Failed to compute diff for {dataset}/{run_id}/L{level}: {e}")
                        continue

                # Consistency check
                if args.consistency and level > 0:
                    try:
                        checker = ConsistencyChecker()
                        coarse_level = level - 1
                        if coarse_level in levels:
                            consistency_output = output_dir / dataset / run_id / f"L{level}_consistency.png"
                            consistency_result = checker.check_consistency(
                                reader, dataset, run_id, level, coarse_level, consistency_output, args.canvas_size
                            )
                            logger.info(f"Consistency result for {dataset}/{run_id}/L{level} vs L{coarse_level}: {consistency_result}")
                    except Exception as e:
                        logger.error(f"Failed to check consistency for {dataset}/{run_id}/L{level}: {e}")
                        continue

    # Save metrics
    if args.metrics and all_metrics:
        metrics_path = output_dir / "metrics.json"
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        with metrics_path.open("w") as f:
            json.dump(all_metrics, f, indent=2)

        # Also save as CSV
        if all_metrics:
            import csv
            csv_path = output_dir / "metrics.csv"
            with csv_path.open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=all_metrics[0].keys())
                writer.writeheader()
                writer.writerows(all_metrics)


if __name__ == "__main__":
    main()
