"""Tests for the tile_processor CLI module."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from him.cli.tile_processor import (
    CoordMode,
    LevelInfo,
    Metrics,
    RenderMode,
    Shape,
    TileData,
    compute_metrics,
    deterministic_color,
    discover_datasets,
    discover_levels,
    discover_run_ids,
    infer_coord_extents,
    load_bin_file,
    load_dataset_info,
    load_level_info,
    load_tiles_for_level,
    map_to_world_coords,
    parse_color,
    parse_shape,
    render_level,
    sort_shapes_deterministic,
)


@pytest.fixture
def sample_tile_root(tmp_path: Path) -> Path:
    """Create a sample tile directory structure."""
    # Create episodic_vector dataset
    ev_dir = tmp_path / "episodic_vector" / "run_001" / "L0" / "x0" / "y0"
    ev_dir.mkdir(parents=True)
    
    # Create a tile with shapes
    tile_data = {
        "shapes": [
            {
                "kind": "circle",
                "center": [0.3, 0.4],
                "radius": 0.1,
                "fill": "#ff0000",
                "alpha": 0.8,
                "weight": 1.0,
                "id": "shape1",
            },
            {
                "kind": "circle",
                "center": [0.6, 0.7],
                "radius": 0.15,
                "fill": "blue",
                "alpha": 0.7,
            },
        ]
    }
    (ev_dir / "tile1.bin").write_text(json.dumps(tile_data))
    
    # Create another tile
    ev_dir2 = tmp_path / "episodic_vector" / "run_001" / "L0" / "x1" / "y0"
    ev_dir2.mkdir(parents=True)
    tile_data2 = {
        "shapes": [
            {
                "kind": "circle",
                "center": [0.5, 0.5],
                "radius": 0.2,
                "fill": "#00ff00",
            }
        ]
    }
    (ev_dir2 / "tile1.bin").write_text(json.dumps(tile_data2))
    
    # Create L1 level
    l1_dir = tmp_path / "episodic_vector" / "run_001" / "L1" / "x0" / "y0"
    l1_dir.mkdir(parents=True)
    l1_tile = {
        "shapes": [
            {
                "kind": "circle",
                "center": [0.5, 0.5],
                "radius": 0.3,
            }
        ]
    }
    (l1_dir / "tile1.bin").write_text(json.dumps(l1_tile))
    
    # Create hormonal_state dataset
    hs_dir = tmp_path / "hormonal_state" / "run_002" / "L0" / "x0" / "y0"
    hs_dir.mkdir(parents=True)
    hs_tile = {
        "shapes": [
            {
                "kind": "circle",
                "center": [0.4, 0.4],
                "radius": 0.12,
                "channel": "dopamine",
            }
        ]
    }
    (hs_dir / "tile1.bin").write_text(json.dumps(hs_tile))
    
    return tmp_path


class TestDiscovery:
    """Test directory discovery functions."""
    
    def test_discover_datasets(self, sample_tile_root: Path) -> None:
        datasets = discover_datasets(sample_tile_root)
        assert "episodic_vector" in datasets
        assert "hormonal_state" in datasets
    
    def test_discover_run_ids(self, sample_tile_root: Path) -> None:
        run_ids = discover_run_ids(sample_tile_root, "episodic_vector")
        assert "run_001" in run_ids
        
        run_ids = discover_run_ids(sample_tile_root, "hormonal_state")
        assert "run_002" in run_ids
    
    def test_discover_levels(self, sample_tile_root: Path) -> None:
        levels = discover_levels(sample_tile_root, "episodic_vector", "run_001")
        assert 0 in levels
        assert 1 in levels
        
    def test_discover_nonexistent(self, sample_tile_root: Path) -> None:
        assert discover_datasets(sample_tile_root / "nonexistent") == []
        assert discover_run_ids(sample_tile_root, "nonexistent") == []
        assert discover_levels(sample_tile_root, "episodic_vector", "nonexistent") == []


class TestParsing:
    """Test parsing functions."""
    
    def test_parse_shape_circle(self) -> None:
        shape_dict = {
            "kind": "circle",
            "center": [0.3, 0.4],
            "radius": 0.1,
            "fill": "#ff0000",
            "alpha": 0.8,
            "weight": 1.0,
            "id": "shape1",
        }
        shape = parse_shape(shape_dict)
        assert shape is not None
        assert shape.kind == "circle"
        assert shape.center == (0.3, 0.4)
        assert shape.radius == 0.1
        assert shape.fill == "#ff0000"
        assert shape.alpha == 0.8
        assert shape.weight == 1.0
        assert shape.id == "shape1"
    
    def test_parse_shape_defaults(self) -> None:
        shape_dict = {"kind": "circle"}
        shape = parse_shape(shape_dict)
        assert shape is not None
        assert shape.center == (0.5, 0.5)  # default center
        assert shape.radius == 0.1  # default radius
        assert shape.alpha == 1.0
        assert shape.weight == 1.0
    
    def test_parse_shape_with_points(self) -> None:
        shape_dict = {
            "kind": "polygon",
            "points": [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]],
        }
        shape = parse_shape(shape_dict)
        assert shape is not None
        # Center derived from average of points
        assert 0.2 < shape.center[0] < 0.4
        assert 0.3 < shape.center[1] < 0.5
    
    def test_load_bin_file(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test.bin"
        test_file.write_text('{"shapes": [{"kind": "circle"}]}')
        data = load_bin_file(test_file)
        assert data is not None
        assert "shapes" in data
    
    def test_load_bin_file_invalid_json(self, tmp_path: Path) -> None:
        test_file = tmp_path / "bad.bin"
        test_file.write_text("not valid json")
        data = load_bin_file(test_file)
        assert data is None


class TestCoordinateMapping:
    """Test coordinate mapping functions."""
    
    def test_map_to_world_normalized(self) -> None:
        shape = Shape(
            kind="circle",
            center=(0.5, 0.5),
            radius=0.1,
        )
        world_x, world_y, world_r = map_to_world_coords(
            shape, tile_x=0, tile_y=0, nx=2, ny=2,
            coord_mode=CoordMode.NORMALIZED,
        )
        assert world_x == 0.25  # (0 + 0.5) / 2
        assert world_y == 0.25
        assert world_r == 0.05  # 0.1 / max(2, 2)
    
    def test_map_to_world_with_offset(self) -> None:
        shape = Shape(
            kind="circle",
            center=(0.5, 0.5),
            radius=0.1,
        )
        world_x, world_y, world_r = map_to_world_coords(
            shape, tile_x=1, tile_y=1, nx=2, ny=2,
            coord_mode=CoordMode.NORMALIZED,
        )
        assert world_x == 0.75  # (1 + 0.5) / 2
        assert world_y == 0.75
    
    def test_infer_coord_extents(self) -> None:
        shapes = [
            Shape(kind="circle", center=(0.2, 0.3), radius=0.1),
            Shape(kind="circle", center=(0.8, 0.7), radius=0.15),
        ]
        min_x, min_y, max_x, max_y = infer_coord_extents(shapes)
        assert min_x == pytest.approx(0.1)  # 0.2 - 0.1
        assert min_y == pytest.approx(0.2)  # 0.3 - 0.1
        assert max_x == pytest.approx(0.95)  # 0.8 + 0.15
        assert max_y == pytest.approx(0.85)  # 0.7 + 0.15


class TestColors:
    """Test color parsing."""
    
    def test_parse_hex_color(self) -> None:
        assert parse_color("#ff0000") == (255, 0, 0)
        assert parse_color("#00ff00") == (0, 255, 0)
        assert parse_color("#0000ff") == (0, 0, 255)
    
    def test_parse_short_hex_color(self) -> None:
        assert parse_color("#f00") == (255, 0, 0)
        assert parse_color("#0f0") == (0, 255, 0)
    
    def test_parse_named_color(self) -> None:
        assert parse_color("red") == (255, 0, 0)
        assert parse_color("blue") == (0, 0, 255)
        assert parse_color("green") == (0, 255, 0)
    
    def test_parse_rgb_notation(self) -> None:
        assert parse_color("rgb(255, 128, 64)") == (255, 128, 64)
    
    def test_parse_invalid_color(self) -> None:
        assert parse_color("invalid") == (128, 128, 128)  # default
        assert parse_color(None) == (128, 128, 128)
    
    def test_deterministic_color(self) -> None:
        shape = Shape(kind="circle", center=(0.5, 0.5), radius=0.1)
        color1 = deterministic_color(shape, 0)
        color2 = deterministic_color(shape, 0)
        assert color1 == color2  # Same shape should get same color


class TestSorting:
    """Test deterministic sorting."""
    
    def test_sort_by_id(self) -> None:
        shapes = [
            Shape(kind="circle", center=(0.5, 0.5), radius=0.1, id="z"),
            Shape(kind="circle", center=(0.5, 0.5), radius=0.1, id="a"),
            Shape(kind="circle", center=(0.5, 0.5), radius=0.1, id="m"),
        ]
        sorted_shapes = sort_shapes_deterministic(shapes)
        assert sorted_shapes[0].id == "a"
        assert sorted_shapes[1].id == "m"
        assert sorted_shapes[2].id == "z"
    
    def test_sort_id_before_no_id(self) -> None:
        shapes = [
            Shape(kind="circle", center=(0.5, 0.5), radius=0.1),  # no id
            Shape(kind="circle", center=(0.5, 0.5), radius=0.1, id="a"),
        ]
        sorted_shapes = sort_shapes_deterministic(shapes)
        assert sorted_shapes[0].id == "a"
        assert sorted_shapes[1].id is None
    
    def test_sort_deterministic_without_id(self) -> None:
        shapes = [
            Shape(kind="circle", center=(0.8, 0.8), radius=0.2),
            Shape(kind="circle", center=(0.2, 0.2), radius=0.1),
        ]
        sorted1 = sort_shapes_deterministic(shapes)
        sorted2 = sort_shapes_deterministic(shapes[::-1])
        # Should be in same order regardless of input order
        assert [s.center for s in sorted1] == [s.center for s in sorted2]


class TestLoading:
    """Test tile loading functions."""
    
    def test_load_tiles_for_level(self, sample_tile_root: Path) -> None:
        tiles = load_tiles_for_level(
            sample_tile_root, "episodic_vector", "run_001", level=0
        )
        assert len(tiles) == 2
        
        # Check tile coordinates
        coords = {(t.tile_x, t.tile_y) for t in tiles}
        assert (0, 0) in coords
        assert (1, 0) in coords
    
    def test_load_level_info(self, sample_tile_root: Path) -> None:
        level_info = load_level_info(
            sample_tile_root, "episodic_vector", "run_001", level=0
        )
        assert level_info is not None
        assert level_info.level == 0
        assert level_info.nx == 2  # max(0, 1) + 1
        assert level_info.ny == 1  # max(0) + 1
    
    def test_load_dataset_info(self, sample_tile_root: Path) -> None:
        info = load_dataset_info(sample_tile_root, "episodic_vector", "run_001")
        assert info is not None
        assert info.name == "episodic_vector"
        assert info.run_id == "run_001"
        assert 0 in info.levels
        assert 1 in info.levels


class TestRendering:
    """Test rendering functions."""
    
    def test_render_level_produces_image(self, sample_tile_root: Path) -> None:
        level_info = load_level_info(
            sample_tile_root, "episodic_vector", "run_001", level=0
        )
        assert level_info is not None
        
        img = render_level(level_info, canvas_size=256)
        assert img.size == (256, 256)
        assert img.mode == "RGBA"
    
    def test_render_different_modes(self, sample_tile_root: Path) -> None:
        level_info = load_level_info(
            sample_tile_root, "episodic_vector", "run_001", level=0
        )
        assert level_info is not None
        
        for mode in [RenderMode.DEFAULT, RenderMode.WEIGHT, RenderMode.UNCERTAINTY]:
            img = render_level(level_info, canvas_size=128, render_mode=mode)
            assert img.size == (128, 128)


class TestMetrics:
    """Test metrics computation."""
    
    def test_compute_metrics(self, sample_tile_root: Path) -> None:
        level_info = load_level_info(
            sample_tile_root, "episodic_vector", "run_001", level=0
        )
        assert level_info is not None
        
        metrics = compute_metrics(level_info, "episodic_vector", "run_001")
        assert metrics.dataset == "episodic_vector"
        assert metrics.run_id == "run_001"
        assert metrics.level == 0
        assert metrics.shape_count == 3  # 2 in first tile + 1 in second
        assert metrics.total_mass > 0
        assert 0 <= metrics.coverage <= 1
        assert 0 <= metrics.center_of_mass[0] <= 1
        assert 0 <= metrics.center_of_mass[1] <= 1


class TestRobustness:
    """Test robustness with bad data."""
    
    def test_handles_bad_json(self, tmp_path: Path) -> None:
        # Create a structure with a bad file
        bad_dir = tmp_path / "dataset" / "run" / "L0" / "x0" / "y0"
        bad_dir.mkdir(parents=True)
        (bad_dir / "bad.bin").write_text("not json")
        (bad_dir / "good.bin").write_text('{"shapes": [{"kind": "circle", "center": [0.5, 0.5], "radius": 0.1}]}')
        
        tiles = load_tiles_for_level(tmp_path, "dataset", "run", 0)
        # Should still load the good tile
        assert len(tiles) == 1
    
    def test_handles_empty_shapes(self, tmp_path: Path) -> None:
        dir_path = tmp_path / "dataset" / "run" / "L0" / "x0" / "y0"
        dir_path.mkdir(parents=True)
        (dir_path / "tile.bin").write_text('{"shapes": []}')
        
        tiles = load_tiles_for_level(tmp_path, "dataset", "run", 0)
        # Should not load tiles with no shapes
        assert len(tiles) == 0
    
    def test_handles_invalid_shape_data(self, tmp_path: Path) -> None:
        dir_path = tmp_path / "dataset" / "run" / "L0" / "x0" / "y0"
        dir_path.mkdir(parents=True)
        # Shapes is not a list
        (dir_path / "tile.bin").write_text('{"shapes": "invalid"}')
        
        tiles = load_tiles_for_level(tmp_path, "dataset", "run", 0)
        assert len(tiles) == 0
