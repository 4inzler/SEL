"""Structured vision analysis utilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _coerce_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_int(value: object) -> Optional[int]:
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return None
    if coerced < 0:
        return None
    return coerced


def _coerce_str(value: object) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return str(value).strip() or None


def _coerce_str_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        items = []
        for item in value:
            text = _coerce_str(item)
            if text:
                items.append(text)
        return items
    if isinstance(value, str):
        return [chunk.strip() for chunk in value.split(",") if chunk.strip()]
    text = _coerce_str(value)
    return [text] if text else []


def dedupe_preserve_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        cleaned = item.strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result


def _single_line(text: str) -> str:
    return " ".join(text.split())


def compact_multiline(text: str) -> str:
    return " / ".join([line.strip() for line in text.splitlines() if line.strip()])


def truncate_text(text: str, max_len: int = 240) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


@dataclass
class VisionText:
    present: bool = False
    content: Optional[str] = None
    language: Optional[str] = None
    legibility: Optional[str] = None
    confidence: float = 0.0


@dataclass
class VisionPerson:
    count: Optional[int] = None
    details: Optional[str] = None


@dataclass
class VisionObject:
    label: str
    count: Optional[int] = None
    attributes: list[str] = field(default_factory=list)


@dataclass
class VisionAnalysis:
    summary: str = ""
    setting: Optional[str] = None
    style: Optional[str] = None
    actions: list[str] = field(default_factory=list)
    objects: list[VisionObject] = field(default_factory=list)
    people: VisionPerson = field(default_factory=VisionPerson)
    text: VisionText = field(default_factory=VisionText)
    notable_details: list[str] = field(default_factory=list)
    uncertainties: list[str] = field(default_factory=list)
    confidence: float = 0.0


def coerce_vision_analysis(raw: object) -> VisionAnalysis:
    if isinstance(raw, VisionAnalysis):
        return raw
    if not isinstance(raw, dict):
        summary = _coerce_str(raw) or ""
        return VisionAnalysis(summary=summary)

    summary = _coerce_str(raw.get("summary") or raw.get("description") or raw.get("caption")) or ""
    setting = _coerce_str(raw.get("setting") or raw.get("scene") or raw.get("location"))
    style = _coerce_str(raw.get("style") or raw.get("visual_style"))
    actions = dedupe_preserve_order(
        _coerce_str_list(raw.get("actions") or raw.get("activity") or raw.get("action"))
    )

    objects_raw = raw.get("objects") or raw.get("items") or raw.get("entities") or []
    objects: list[VisionObject] = []
    for item in objects_raw:
        if isinstance(item, str):
            label = item.strip()
            if label:
                objects.append(VisionObject(label=label))
            continue
        if isinstance(item, dict):
            label = _coerce_str(
                item.get("label") or item.get("name") or item.get("object") or item.get("item")
            )
            if not label:
                continue
            count = _coerce_int(item.get("count") or item.get("quantity"))
            attrs = dedupe_preserve_order(
                _coerce_str_list(item.get("attributes") or item.get("attrs") or item.get("details"))
            )
            objects.append(VisionObject(label=label, count=count, attributes=attrs))

    people_raw = raw.get("people") or raw.get("person")
    people = VisionPerson()
    if isinstance(people_raw, dict):
        people.count = _coerce_int(people_raw.get("count"))
        people.details = _coerce_str(people_raw.get("details") or people_raw.get("description"))
    elif isinstance(people_raw, (int, float)):
        people.count = _coerce_int(people_raw)
    elif isinstance(people_raw, str):
        people.details = people_raw.strip() or None

    text_raw = raw.get("text")
    text = VisionText()
    if isinstance(text_raw, dict):
        present_flag = text_raw.get("present") or text_raw.get("has_text")
        text.present = bool(present_flag)
        content = _coerce_str(text_raw.get("content") or text_raw.get("value") or text_raw.get("text"))
        if content:
            text.present = True
            text.content = content
        text.language = _coerce_str(text_raw.get("language") or text_raw.get("lang"))
        text.legibility = _coerce_str(text_raw.get("legibility") or text_raw.get("clarity"))
        text.confidence = _clamp01(_coerce_float(text_raw.get("confidence"), default=0.0))
    elif isinstance(text_raw, str):
        cleaned = text_raw.strip()
        if cleaned:
            text.present = True
            text.content = cleaned
    elif isinstance(text_raw, bool):
        text.present = text_raw

    notable_details = dedupe_preserve_order(
        _coerce_str_list(raw.get("notable_details") or raw.get("details") or raw.get("highlights"))
    )
    uncertainties = dedupe_preserve_order(
        _coerce_str_list(raw.get("uncertainties") or raw.get("uncertain") or raw.get("unknowns"))
    )
    confidence = _clamp01(_coerce_float(raw.get("confidence") or raw.get("overall_confidence"), default=0.0))

    return VisionAnalysis(
        summary=summary,
        setting=setting,
        style=style,
        actions=actions,
        objects=objects,
        people=people,
        text=text,
        notable_details=notable_details,
        uncertainties=uncertainties,
        confidence=confidence,
    )


def apply_text_override(
    analysis: VisionAnalysis,
    text: Optional[str],
    *,
    confidence: float = 0.95,
    legibility: str = "clear",
) -> VisionAnalysis:
    if text:
        analysis.text.present = True
        analysis.text.content = text.strip()
        analysis.text.legibility = legibility
        analysis.text.confidence = _clamp01(confidence)
    return analysis


def _format_objects(objects: list[VisionObject], max_objects: int) -> str:
    if not objects:
        return ""
    formatted: list[str] = []
    for obj in objects[:max_objects]:
        label = obj.label.strip()
        if not label:
            continue
        desc = label
        if obj.count is not None:
            desc += f" x{obj.count}"
        if obj.attributes:
            attrs = ", ".join(obj.attributes[:2])
            desc += f" ({attrs})"
        formatted.append(desc)
    if not formatted:
        return ""
    extra = len(objects) - len(formatted)
    if extra > 0:
        formatted.append(f"+{extra} more")
    return ", ".join(formatted)


def _format_list(items: list[str], max_items: int) -> str:
    if not items:
        return ""
    trimmed = items[:max_items]
    extra = len(items) - len(trimmed)
    text = ", ".join(trimmed)
    if extra > 0:
        text = f"{text}, +{extra} more"
    return text


def render_vision_analysis(
    analysis: VisionAnalysis,
    *,
    max_objects: int = 6,
    max_actions: int = 4,
    max_details: int = 4,
    max_uncertainties: int = 3,
) -> str:
    parts: list[str] = []

    if analysis.summary:
        summary = truncate_text(_single_line(analysis.summary), 200)
        parts.append(f"Summary: {summary}")

    people_bits: list[str] = []
    if analysis.people.count is not None:
        people_bits.append(str(analysis.people.count))
    if analysis.people.details:
        people_bits.append(_single_line(analysis.people.details))
    if people_bits:
        parts.append(f"People: {'; '.join(people_bits)}")

    objects_text = _format_objects(analysis.objects, max_objects)
    if objects_text:
        parts.append(f"Objects: {objects_text}")

    actions_text = _format_list(analysis.actions, max_actions)
    if actions_text:
        parts.append(f"Actions: {actions_text}")

    if analysis.setting:
        parts.append(f"Setting: {truncate_text(_single_line(analysis.setting), 120)}")

    if analysis.style:
        parts.append(f"Style: {truncate_text(_single_line(analysis.style), 80)}")

    if analysis.text.present:
        if analysis.text.content:
            text_content = compact_multiline(analysis.text.content)
            text_content = truncate_text(text_content, 200)
            text_bits = [f"\"{text_content}\""]
        else:
            text_bits = ["present but unreadable"]
        if analysis.text.legibility and analysis.text.legibility != "clear":
            text_bits.append(analysis.text.legibility)
        if analysis.text.language:
            text_bits.append(analysis.text.language)
        parts.append(f"Text: {'; '.join(text_bits)}")

    details_text = _format_list(analysis.notable_details, max_details)
    if details_text:
        parts.append(f"Details: {details_text}")

    uncertainties_text = _format_list(analysis.uncertainties, max_uncertainties)
    if uncertainties_text:
        parts.append(f"Uncertain: {uncertainties_text}")

    if analysis.confidence and analysis.confidence < 0.5:
        parts.append(f"Confidence: {analysis.confidence:.2f}")

    return " | ".join(parts)
