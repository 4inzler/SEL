"""
Video frame extraction and analysis using ffmpeg.

Downloads short video attachments, extracts evenly-spaced frames via ffmpeg,
and analyses them with the vision LLM — same pipeline as GIF analysis.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import httpx

from .media_utils import VIDEO_MAX_BYTES, looks_like_video_url

logger = logging.getLogger(__name__)

_FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
_FFPROBE = shutil.which("ffprobe") or "ffprobe"


def _run(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, timeout=timeout)


def _probe_duration(path: str) -> Optional[float]:
    """Return video duration in seconds using ffprobe, or None on failure."""
    try:
        result = _run([
            _FFPROBE, "-v", "quiet",
            "-print_format", "json",
            "-show_streams", "-select_streams", "v:0",
            path,
        ])
        data = json.loads(result.stdout)
        for stream in data.get("streams", []):
            dur = stream.get("duration")
            if dur:
                return float(dur)
    except Exception as exc:
        logger.debug("ffprobe failed: %s", exc)
    return None


def _extract_frames(video_path: str, out_dir: str, n_frames: int = 5) -> list[str]:
    """
    Extract up to n_frames evenly-spaced frames from the video.

    Returns a sorted list of output PNG file paths.
    """
    duration = _probe_duration(video_path)
    if duration and duration > 0:
        # Place frames at evenly-spaced timestamps across the video
        interval = duration / (n_frames + 1)
        select_expr = "+".join(
            f"eq(t\\,{interval * (i + 1):.3f})" for i in range(n_frames)
        )
        vf = f"select='{select_expr}',scale=iw:ih"
        result = _run([
            _FFMPEG, "-i", video_path,
            "-vf", vf,
            "-vsync", "vfr",
            "-frames:v", str(n_frames),
            "-q:v", "2",
            f"{out_dir}/frame_%03d.png",
        ], timeout=60)
    else:
        # Fallback: one frame every 2 seconds
        result = _run([
            _FFMPEG, "-i", video_path,
            "-vf", f"fps=0.5,scale=iw:ih",
            "-frames:v", str(n_frames),
            "-q:v", "2",
            f"{out_dir}/frame_%03d.png",
        ], timeout=60)

    if result.returncode != 0:
        logger.warning("ffmpeg frame extraction failed: %s", result.stderr.decode(errors="replace")[:300])

    paths = sorted(Path(out_dir).glob("frame_*.png"))
    return [str(p) for p in paths]


class VideoAnalyzer:
    """Analyses short video clips by extracting and describing key frames."""

    def __init__(self, max_frames: int = 5, max_bytes: int = VIDEO_MAX_BYTES):
        self.max_frames = max_frames
        self.max_bytes = max_bytes

    def is_video(self, url: str, content_type: Optional[str] = None) -> bool:
        return looks_like_video_url(url, content_type)

    async def download_video(self, url: str) -> Optional[bytes]:
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                # Stream to check size before buffering the whole thing
                async with client.stream("GET", url) as resp:
                    resp.raise_for_status()
                    content_length = int(resp.headers.get("content-length", 0))
                    if content_length and content_length > self.max_bytes:
                        logger.info("Video too large (%d bytes), skipping", content_length)
                        return None
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in resp.aiter_bytes(chunk_size=65536):
                        total += len(chunk)
                        if total > self.max_bytes:
                            logger.info("Video exceeded %d bytes mid-download, skipping", self.max_bytes)
                            return None
                        chunks.append(chunk)
                    return b"".join(chunks)
        except Exception as exc:
            logger.warning("Failed to download video from %s: %s", url, exc)
            return None

    async def analyze_video(self, video_url: str, llm_client) -> Optional[str]:
        """
        Download the video, extract frames, analyse each with the vision model,
        and return a combined description.
        """
        data = await self.download_video(video_url)
        if not data:
            return None

        suffix = Path(video_url.split("?")[0]).suffix or ".mp4"
        with tempfile.TemporaryDirectory() as tmp:
            video_path = str(Path(tmp) / f"video{suffix}")
            Path(video_path).write_bytes(data)

            frame_paths = await asyncio.get_event_loop().run_in_executor(
                None, _extract_frames, video_path, tmp, self.max_frames
            )

            if not frame_paths:
                logger.warning("No frames extracted from video %s", video_url)
                return None

            logger.info("Extracted %d frames from video %s", len(frame_paths), video_url)

            descriptions: list[str] = []
            for i, path in enumerate(frame_paths):
                try:
                    analysis = await llm_client.analyze_image(
                        f"file://{path}",
                        prompt=f"Frame {i + 1}/{len(frame_paths)} of a short video clip. Describe what you see.",
                    )
                    if analysis.summary:
                        descriptions.append(analysis.summary)
                except Exception as exc:
                    logger.warning("Failed to analyse video frame %s: %s", path, exc)

        if not descriptions:
            return None

        if len(descriptions) == 1:
            return f"Video clip: {descriptions[0]}"

        frames_text = " / ".join(descriptions[:5])
        return f"Video clip ({len(descriptions)} frames): {frames_text}"
