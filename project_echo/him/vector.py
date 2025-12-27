"""Utilities for building vector-based tiles from a single image."""
from __future__ import annotations

import base64
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple
from xml.etree import ElementTree as ET

from .models import TileIngestRecord, TilePayload


def _strip_namespace(tag: str) -> str:
    """Return the SVG element name without the XML namespace."""

    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _parse_float(value: str | None, default: float = 0.0) -> float:
    if value is None:
        return default
    value = value.strip()
    for suffix in ("px", "pt", "cm", "mm", "in"):
        if value.endswith(suffix):
            value = value[: -len(suffix)]
            break
    if value == "":
        return default
    return float(value)


def _parse_points(value: str | None) -> List[Tuple[float, float]]:
    if not value:
        return []
    cleaned = value.replace(",", " ")
    parts = [part for part in cleaned.split() if part]
    if len(parts) % 2 != 0:
        raise ValueError("Malformed SVG points attribute")
    it = iter(parts)
    return [(float(x), float(y)) for x, y in zip(it, it)]


@dataclass(slots=True)
class Canvas:
    """Viewport used to normalise coordinates."""

    min_x: float
    min_y: float
    width: float
    height: float


@dataclass(slots=True)
class VectorShape:
    """Basic vector primitive extracted from an SVG document."""

    kind: str
    points: List[Tuple[float, float]]
    stroke: str | None
    fill: str | None

    def bounding_box(self) -> Tuple[float, float, float, float]:
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        return (min(xs), min(ys), max(xs), max(ys))

    def to_tile_payload(
        self, origin_x: float, origin_y: float, span: float
    ) -> Dict[str, object]:
        local = [
            [
                (point[0] - origin_x) / span if span else 0.0,
                (point[1] - origin_y) / span if span else 0.0,
            ]
            for point in self.points
        ]
        return {
            "kind": self.kind,
            "points": local,
            "stroke": self.stroke,
            "fill": self.fill,
        }


@dataclass(slots=True)
class VectorScene:
    """Normalised representation of a vector image."""

    canvas: Canvas
    shapes: List[VectorShape]


def _normalise_points(
    points: Sequence[Tuple[float, float]], canvas: Canvas
) -> List[Tuple[float, float]]:
    if not canvas.width or not canvas.height:
        raise ValueError("Canvas width and height must be non-zero")
    return [
        (
            (x - canvas.min_x) / canvas.width,
            (y - canvas.min_y) / canvas.height,
        )
        for x, y in points
    ]


def _parse_svg_shape(element: ET.Element, canvas: Canvas) -> VectorShape | None:
    tag = _strip_namespace(element.tag)
    stroke = element.attrib.get("stroke")
    fill = element.attrib.get("fill")

    if tag == "rect":
        width = _parse_float(element.attrib.get("width"))
        height = _parse_float(element.attrib.get("height"))
        if not width or not height:
            return None
        x = _parse_float(element.attrib.get("x"))
        y = _parse_float(element.attrib.get("y"))
        points = [
            (x, y),
            (x + width, y),
            (x + width, y + height),
            (x, y + height),
        ]
    elif tag == "line":
        x1 = _parse_float(element.attrib.get("x1"))
        y1 = _parse_float(element.attrib.get("y1"))
        x2 = _parse_float(element.attrib.get("x2"))
        y2 = _parse_float(element.attrib.get("y2"))
        points = [(x1, y1), (x2, y2)]
    elif tag == "circle":
        cx = _parse_float(element.attrib.get("cx"))
        cy = _parse_float(element.attrib.get("cy"))
        r = _parse_float(element.attrib.get("r"))
        if not r:
            return None
        samples = 16
        points = [
            (
                cx + math.cos(2 * math.pi * idx / samples) * r,
                cy + math.sin(2 * math.pi * idx / samples) * r,
            )
            for idx in range(samples)
        ]
    elif tag in {"polyline", "polygon"}:
        points = _parse_points(element.attrib.get("points"))
        if tag == "polygon" and points and points[0] != points[-1]:
            points.append(points[0])
        if not points:
            return None
    else:
        return None

    normalised = _normalise_points(points, canvas)
    return VectorShape(kind=tag, points=normalised, stroke=stroke, fill=fill)


def load_svg_scene(svg_path: Path | str) -> VectorScene:
    """Parse an SVG document and normalise it into a :class:`VectorScene`."""

    path = Path(svg_path)
    content = path.read_text(encoding="utf-8")
    return svg_to_scene(content)


def svg_to_scene(svg_markup: str) -> VectorScene:
    """Convert SVG markup into a normalised vector scene."""

    root = ET.fromstring(svg_markup)
    view_box = root.attrib.get("viewBox")
    if view_box:
        parts = [float(part) for part in view_box.replace(",", " ").split() if part]
        if len(parts) != 4:
            raise ValueError("SVG viewBox must define four numbers")
        min_x, min_y, width, height = parts
    else:
        width = _parse_float(root.attrib.get("width"), default=1.0)
        height = _parse_float(root.attrib.get("height"), default=1.0)
        min_x = _parse_float(root.attrib.get("x"), default=0.0)
        min_y = _parse_float(root.attrib.get("y"), default=0.0)
    canvas = Canvas(min_x=min_x, min_y=min_y, width=width, height=height)

    shapes: List[VectorShape] = []
    for element in root.iter():
        if element is root:
            continue
        shape = _parse_svg_shape(element, canvas)
        if shape is not None:
            shapes.append(shape)

    if not shapes:
        raise ValueError("SVG document does not contain any supported vector primitives")
    return VectorScene(canvas=canvas, shapes=shapes)


def scene_to_tiles(
    scene: VectorScene,
    *,
    snapshot_id: str,
    stream: str = "vector_scene",
    max_level: int = 4,
) -> List[TileIngestRecord]:
    """Generate tile ingest records that capture the vector scene at multiple scales."""

    if max_level < 0:
        raise ValueError("max_level must be non-negative")

    records: List[TileIngestRecord] = []
    for level in range(max_level + 1):
        tile_count = 1 << level
        span = 1.0 / tile_count if tile_count else 1.0
        tiles: Dict[Tuple[int, int], List[Dict[str, object]]] = {}

        for shape in scene.shapes:
            min_x, min_y, max_x, max_y = shape.bounding_box()
            min_tile_x = max(0, min(tile_count - 1, int(math.floor(min_x * tile_count))))
            max_tile_x = max(0, min(tile_count - 1, int(math.ceil(max_x * tile_count) - 1)))
            min_tile_y = max(0, min(tile_count - 1, int(math.floor(min_y * tile_count))))
            max_tile_y = max(0, min(tile_count - 1, int(math.ceil(max_y * tile_count) - 1)))

            for tile_x in range(min_tile_x, max_tile_x + 1):
                for tile_y in range(min_tile_y, max_tile_y + 1):
                    origin_x = tile_x * span
                    origin_y = tile_y * span
                    payload = shape.to_tile_payload(origin_x, origin_y, span)
                    tiles.setdefault((tile_x, tile_y), []).append(payload)

        for (tile_x, tile_y), payload_shapes in tiles.items():
            payload_dict = {
                "level": level,
                "tile": [tile_x, tile_y],
                "origin": [tile_x * span, tile_y * span],
                "span": span,
                "shapes": payload_shapes,
            }
            raw = json.dumps(payload_dict, sort_keys=True).encode("utf-8")
            record = TileIngestRecord(
                stream=stream,
                snapshot_id=snapshot_id,
                level=level,
                x=tile_x,
                y=tile_y,
                shape=(len(payload_shapes), 1, 1),
                dtype="vector/json",
                payload=TilePayload(bytes_b64=base64.b64encode(raw).decode("utf-8")),
            )
            records.append(record)

    return records


def svg_to_tiles(
    svg_markup: str,
    *,
    snapshot_id: str,
    stream: str = "vector_scene",
    max_level: int = 4,
) -> List[TileIngestRecord]:
    """Convenience wrapper that converts SVG markup directly into tiles."""

    scene = svg_to_scene(svg_markup)
    return scene_to_tiles(scene, snapshot_id=snapshot_id, stream=stream, max_level=max_level)


def ingest_svg(
    store,  # HierarchicalImageMemory (runtime import to avoid cycle)
    svg_markup: str,
    *,
    snapshot_id: str,
    stream: str = "vector_scene",
    max_level: int = 4,
) -> None:
    """Ingest SVG markup directly into a HierarchicalImageMemory instance."""

    records = svg_to_tiles(svg_markup, snapshot_id=snapshot_id, stream=stream, max_level=max_level)
    store.put_tiles(records)


__all__ = [
    "Canvas",
    "VectorScene",
    "VectorShape",
    "ingest_svg",
    "load_svg_scene",
    "scene_to_tiles",
    "svg_to_scene",
    "svg_to_tiles",
]
