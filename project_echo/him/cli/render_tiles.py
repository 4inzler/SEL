"""Render stitched HIM tiles from directory roots and compute metrics."""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Dict, Iterable, Sequence

from ..rendering import (
    LevelSpec,
    RenderResult,
    RenderedLevel,
    build_layouts,
    consistency_checks,
    diff_rendered_levels,
    discover_tiles,
    merge_specs,
    render_layouts,
    write_metrics,
)

logger = logging.getLogger(__name__)


def _render_root(
    root: Path,
    *,
    coord_mode: str,
    canvas_size: int,
    render_modes: Sequence[str],
    spec_overrides: Dict[tuple[str, str, int], LevelSpec] | None,
) -> RenderResult:
    records = discover_tiles(root)
    layouts = build_layouts(records, coord_mode=coord_mode)
    renders = render_layouts(
        layouts,
        canvas_size=canvas_size,
        render_modes=render_modes,
        spec_overrides=spec_overrides,
    )
    return RenderResult(root=root, layouts=layouts, renders=renders)


def _save_renders(result: RenderResult, output_dir: Path) -> None:
    for key, modes in result.renders.items():
        dataset, run_id, level = key
        base_dir = output_dir / dataset / run_id
        base_dir.mkdir(parents=True, exist_ok=True)
        for mode, render in modes.items():
            path = base_dir / f"L{level}_{mode}.png"
            render.image.save(path)


def _collect_metrics(result: RenderResult) -> Iterable:
    for key, modes in result.renders.items():
        default_mode = "default" if "default" in modes else next(iter(modes))
        yield modes[default_mode].metrics


def _shared_specs(first: RenderResult, second: RenderResult) -> Dict[tuple[str, str, int], LevelSpec]:
    shared = {}
    for key, layout in first.layouts.items():
        other = second.layouts.get(key)
        shared[key] = merge_specs(layout.spec, other.spec if other else None)
    for key, layout in second.layouts.items():
        if key in shared:
            continue
        shared[key] = merge_specs(layout.spec, None)
    return shared


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Render stitched HIM tiles stored in directories")
    parser.add_argument("root", help="Directory containing dataset folders (episodic_vector, hormonal_state, ...)")
    parser.add_argument("--output", default="renders", help="Directory to write rendered assets and reports")
    parser.add_argument("--coord-mode", choices=["auto", "normalized", "pixel"], default="auto")
    parser.add_argument("--render-modes", default="default", help="Comma-separated render modes (default,weight,uncertainty,vectors)")
    parser.add_argument("--canvas-size", type=int, default=1024, help="Canvas size in pixels (square)")
    parser.add_argument("--diff-root", help="Optional second root for delta rendering")
    parser.add_argument("--align-window", type=int, default=0, help="Max integer shift for cross-correlation alignment")
    parser.add_argument("--skip-consistency", action="store_true", help="Skip multi-resolution consistency checks")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    root = Path(args.root).expanduser().resolve()
    output_dir = Path(args.output).expanduser().resolve()
    render_modes = tuple(mode.strip() for mode in args.render_modes.split(",") if mode.strip())
    if not render_modes:
        render_modes = ("default",)

    logger.info("Rendering tiles from %s", root)
    secondary_result: RenderResult | None = None
    primary_result = _render_root(
        root,
        coord_mode=args.coord_mode,
        canvas_size=args.canvas_size,
        render_modes=render_modes,
        spec_overrides=None,
    )
    diff_root: Path | None = None
    if args.diff_root:
        diff_root = Path(args.diff_root).expanduser().resolve()
        logger.info("Diff mode enabled; secondary root: %s", diff_root)
        secondary_result = _render_root(
            diff_root,
            coord_mode=args.coord_mode,
            canvas_size=args.canvas_size,
            render_modes=render_modes,
            spec_overrides=None,
        )
        specs = _shared_specs(primary_result, secondary_result)
        primary_result = _render_root(
            root,
            coord_mode=args.coord_mode,
            canvas_size=args.canvas_size,
            render_modes=render_modes,
            spec_overrides=specs,
        )
        secondary_result = _render_root(
            diff_root,
            coord_mode=args.coord_mode,
            canvas_size=args.canvas_size,
            render_modes=render_modes,
            spec_overrides=specs,
        )
    _save_renders(primary_result, output_dir)

    metrics_dir = output_dir / "reports"
    write_metrics(_collect_metrics(primary_result), metrics_dir)
    if not args.skip_consistency:
        consistency_checks(primary_result.renders, output_dir=metrics_dir / "consistency")

    if secondary_result:
        secondary_out = output_dir / "secondary"
        _save_renders(secondary_result, secondary_out)
        write_metrics(_collect_metrics(secondary_result), secondary_out / "reports")
        deltas = diff_rendered_levels(
            primary_result,
            secondary_result,
            output_dir=output_dir / "diff",
            render_modes=render_modes,
            align_window=args.align_window,
        )
        (output_dir / "diff" / "summary.json").write_text(json.dumps(_serialise_paths(deltas), indent=2))


def _serialise_paths(data: Dict) -> Dict:
    return {str(key): {mode: str(path) for mode, path in modes.items()} for key, modes in data.items()}


if __name__ == "__main__":
    main()
