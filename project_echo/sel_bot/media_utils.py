from __future__ import annotations

import base64
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlsplit

IMAGE_EXTENSIONS = {
    ".apng",
    ".avif",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".tiff",
}
GIF_EXTENSIONS = {".gif"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v", ".wmv", ".flv"}
VIDEO_CONTENT_TYPE_PREFIXES = ("video/",)
VIDEO_MAX_BYTES = 50 * 1024 * 1024  # 50 MB


def normalize_content_type(content_type: Optional[str]) -> Optional[str]:
    if not content_type:
        return None
    return content_type.split(";", 1)[0].strip().lower()


def _extension_from_query(query: str) -> str:
    params = parse_qs(query)
    for key in ("format", "ext", "type"):
        value = params.get(key)
        if not value:
            continue
        candidate = value[0].strip().lower()
        if not candidate:
            continue
        if not candidate.startswith("."):
            candidate = f".{candidate}"
        return candidate
    return ""


def url_extension(url: str) -> str:
    try:
        parsed = urlsplit(url)
        ext = Path(parsed.path).suffix.lower()
        if ext:
            return ext
        query_ext = _extension_from_query(parsed.query)
        if query_ext:
            return query_ext
    except Exception:
        pass
    return Path(url).suffix.lower()


def looks_like_image_url(url: str) -> bool:
    ext = url_extension(url)
    return ext in IMAGE_EXTENSIONS


def looks_like_gif_url(url: str, content_type: Optional[str] = None) -> bool:
    normalized = normalize_content_type(content_type)
    if normalized and "gif" in normalized:
        return True
    ext = url_extension(url)
    return ext in GIF_EXTENSIONS


def looks_like_image_filename(filename: str) -> bool:
    return Path(filename).suffix.lower() in IMAGE_EXTENSIONS


def looks_like_gif_filename(filename: str) -> bool:
    return Path(filename).suffix.lower() in GIF_EXTENSIONS


def looks_like_video_url(url: str, content_type: Optional[str] = None) -> bool:
    normalized = normalize_content_type(content_type)
    if normalized and normalized.startswith("video/"):
        return True
    ext = url_extension(url)
    return ext in VIDEO_EXTENSIONS


def looks_like_video_filename(filename: str) -> bool:
    return Path(filename).suffix.lower() in VIDEO_EXTENSIONS


def resolve_image_url(image_url: str) -> str:
    """Convert file:// local paths to base64 data URIs for API delivery."""
    if not image_url.startswith("file://"):
        return image_url
    local_path = Path(image_url[7:])
    suffix = local_path.suffix.lower()
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(suffix, "image/png")
    data = base64.b64encode(local_path.read_bytes()).decode()
    return f"data:{mime};base64,{data}"
