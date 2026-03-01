"""
GIF frame extraction and analysis utilities.

Extracts key frames from animated GIFs and analyzes them to understand
what's happening in the animation.
"""

import io
import logging
import tempfile
from pathlib import Path
from typing import List, Optional

import httpx
from PIL import Image, ImageChops, ImageStat

from .media_utils import looks_like_gif_url
from .vision_analysis import (
    VisionAnalysis,
    apply_text_override,
    compact_multiline,
    dedupe_preserve_order,
    render_vision_analysis,
    truncate_text,
)

logger = logging.getLogger(__name__)


class GifAnalyzer:
    """Analyzes animated GIFs by extracting and describing key frames."""

    def __init__(self, max_frames: int = 5, frame_skip: int = 3):
        """
        Initialize GIF analyzer.

        Args:
            max_frames: Maximum number of frames to extract and analyze
            frame_skip: Skip every N frames (higher = fewer frames analyzed)
        """
        self.max_frames = max_frames
        self.frame_skip = frame_skip

    async def download_gif(self, url: str) -> Optional[bytes]:
        """
        Download GIF from URL.

        Args:
            url: URL to the GIF file

        Returns:
            GIF data as bytes, or None if download fails
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.content
        except Exception as e:
            logger.error(f"Failed to download GIF from {url}: {e}")
            return None

    def extract_frames(self, gif_data: bytes) -> List[Image.Image]:
        """
        Extract key frames from GIF data using change-based sampling.

        Args:
            gif_data: GIF file data as bytes

        Returns:
            List of PIL Image objects representing key frames
        """
        frames = []
        try:
            gif = Image.open(io.BytesIO(gif_data))

            # Get total frame count
            total_frames = 0
            try:
                while True:
                    gif.seek(total_frames)
                    total_frames += 1
            except EOFError:
                pass

            logger.info(f"GIF has {total_frames} total frames")

            if total_frames <= self.max_frames:
                frame_indices = list(range(total_frames))
                for idx in frame_indices:
                    try:
                        gif.seek(idx)
                        frame = gif.convert("RGB")
                        frames.append(frame.copy())
                    except Exception as e:
                        logger.warning(f"Failed to extract frame {idx}: {e}")
                logger.info(f"Extracted {len(frames)} frames from GIF")
                return frames

            step = max(1, self.frame_skip)
            candidates: list[tuple[float, int, Image.Image]] = []
            prev_frame: Optional[Image.Image] = None

            for idx in range(0, total_frames, step):
                try:
                    gif.seek(idx)
                    frame = gif.convert("RGB")
                    score = float("inf") if prev_frame is None else self._frame_diff_score(frame, prev_frame)
                    candidates.append((score, idx, frame.copy()))
                    prev_frame = frame
                except Exception as e:
                    logger.warning(f"Failed to extract frame {idx}: {e}")

            last_idx = total_frames - 1
            if last_idx % step != 0:
                try:
                    gif.seek(last_idx)
                    frame = gif.convert("RGB")
                    score = float("inf") if prev_frame is None else self._frame_diff_score(frame, prev_frame)
                    candidates.append((score, last_idx, frame.copy()))
                except Exception as e:
                    logger.warning(f"Failed to extract last frame {last_idx}: {e}")

            candidates.sort(key=lambda item: item[0], reverse=True)
            selected: dict[int, Image.Image] = {}
            for score, idx, frame in candidates:
                selected[idx] = frame
                if len(selected) >= self.max_frames:
                    break

            if 0 not in selected:
                try:
                    gif.seek(0)
                    selected[0] = gif.convert("RGB").copy()
                except Exception:
                    pass
            if last_idx not in selected:
                try:
                    gif.seek(last_idx)
                    selected[last_idx] = gif.convert("RGB").copy()
                except Exception:
                    pass

            frames = [selected[idx] for idx in sorted(selected)]
            logger.info(f"Extracted {len(frames)} frames from GIF (change-based sampling)")

        except Exception as e:
            logger.error(f"Failed to process GIF: {e}")

        return frames

    @staticmethod
    def _frame_diff_score(frame_a: Image.Image, frame_b: Image.Image) -> float:
        """Compute a simple visual difference score between frames."""
        size = (64, 64)
        small_a = frame_a.resize(size)
        small_b = frame_b.resize(size)
        diff = ImageChops.difference(small_a, small_b)
        stat = ImageStat.Stat(diff)
        return sum(stat.mean) / max(len(stat.mean), 1)

    @staticmethod
    def _format_list(items: list[str], max_items: int) -> str:
        cleaned = [item.strip() for item in items if item.strip()]
        if not cleaned:
            return ""
        trimmed = cleaned[:max_items]
        extra = len(cleaned) - len(trimmed)
        text = ", ".join(trimmed)
        if extra > 0:
            text = f"{text}, +{extra} more"
        return text

    def _combine_frame_analyses(
        self,
        analyses: list[VisionAnalysis],
        ocr_text: Optional[str],
    ) -> Optional[str]:
        if not analyses:
            return None

        summaries = [compact_multiline(analysis.summary) for analysis in analyses if analysis.summary]
        actions = dedupe_preserve_order(
            [action for analysis in analyses for action in analysis.actions]
        )
        objects = dedupe_preserve_order(
            [obj.label for analysis in analyses for obj in analysis.objects if obj.label]
        )
        uncertainties = dedupe_preserve_order(
            [item for analysis in analyses for item in analysis.uncertainties]
        )
        setting = next((analysis.setting for analysis in analyses if analysis.setting), None)

        text = ocr_text
        if not text:
            for analysis in analyses:
                if analysis.text.present and analysis.text.content:
                    text = analysis.text.content
                    break

        parts: list[str] = [f"Animated GIF ({len(analyses)} frames)"]
        if summaries:
            if len(summaries) <= 3:
                parts.append(f"Frames: {' / '.join(summaries)}")
            else:
                parts.append(f"Frames: {' / '.join(summaries[:3])} / ...")
        actions_text = self._format_list(actions, 6)
        if actions_text:
            parts.append(f"Actions: {actions_text}")
        objects_text = self._format_list(objects, 6)
        if objects_text:
            parts.append(f"Objects: {objects_text}")
        if setting:
            parts.append(f"Setting: {truncate_text(compact_multiline(setting), 120)}")
        if text:
            compact = compact_multiline(text)
            parts.append(f"Text: \"{truncate_text(compact, 160)}\"")
        uncertainties_text = self._format_list(uncertainties, 3)
        if uncertainties_text:
            parts.append(f"Uncertain: {uncertainties_text}")

        return " | ".join(parts)

    async def save_frame_as_temp(self, frame: Image.Image, format: str = "PNG") -> Optional[str]:
        """
        Save a frame to a temporary file.

        Args:
            frame: PIL Image to save
            format: Image format (PNG, JPEG, etc.)

        Returns:
            Path to temporary file, or None if save fails
        """
        try:
            # Create temporary file
            temp_file = tempfile.NamedTemporaryFile(
                delete=False,
                suffix=f".{format.lower()}"
            )
            frame.save(temp_file.name, format=format)
            temp_file.close()
            return temp_file.name
        except Exception as e:
            logger.error(f"Failed to save frame to temp file: {e}")
            return None

    async def analyze_gif(
        self,
        gif_url: str,
        llm_client,
        describe_prompt: str = "Describe what's happening in this frame of an animated GIF."
    ) -> Optional[str]:
        """
        Analyze a GIF by describing key frames.

        Args:
            gif_url: URL to the GIF
            llm_client: LLM client with analyze_image method
            describe_prompt: Prompt for frame description

        Returns:
            Combined description of what's happening in the GIF
        """
        # Download GIF
        gif_data = await self.download_gif(gif_url)
        if not gif_data:
            return None

        # Extract frames
        frames = self.extract_frames(gif_data)
        if not frames:
            logger.warning("No frames extracted from GIF")
            return None

        # For single frame (basically a static image)
        if len(frames) == 1:
            try:
                temp_path = await self.save_frame_as_temp(frames[0])
                if temp_path:
                    analysis = await llm_client.analyze_image(
                        f"file://{temp_path}",
                        prompt=describe_prompt,
                    )

                    # Extract text from the frame
                    ocr_text = await llm_client.extract_text_from_image(f"file://{temp_path}")
                    if ocr_text:
                        analysis = apply_text_override(analysis, ocr_text)

                    Path(temp_path).unlink(missing_ok=True)

                    caption = render_vision_analysis(analysis)
                    return caption or analysis.summary or None
            except Exception as e:
                logger.error(f"Failed to analyze single frame: {e}")
                return None

        # For multiple frames, analyze each and combine
        frame_analyses: list[VisionAnalysis] = []
        temp_files = []
        ocr_text = None

        try:
            for i, frame in enumerate(frames):
                temp_path = await self.save_frame_as_temp(frame)
                if temp_path:
                    temp_files.append(temp_path)
                    try:
                        analysis = await llm_client.analyze_image(
                            f"file://{temp_path}",
                            prompt=f"Frame {i+1}/{len(frames)}: {describe_prompt}",
                        )
                        frame_analyses.append(analysis)
                        if analysis.summary:
                            logger.info(
                                "Analyzed frame %s/%s summary=%s",
                                i + 1,
                                len(frames),
                                analysis.summary[:120],
                            )

                        # Extract text from the first frame only (to avoid redundant OCR calls)
                        if i == 0 and not ocr_text:
                            try:
                                ocr_text = await llm_client.extract_text_from_image(f"file://{temp_path}")
                                if ocr_text:
                                    logger.info(f"OCR extracted text from GIF frame 1: {ocr_text[:100]}")
                            except Exception as ocr_error:
                                logger.warning(f"OCR failed on GIF frame: {ocr_error}")

                    except Exception as e:
                        logger.warning(f"Failed to analyze frame {i+1}: {e}")

            combined = self._combine_frame_analyses(frame_analyses, ocr_text)
            return combined

        finally:
            # Cleanup temporary files
            for temp_file in temp_files:
                try:
                    Path(temp_file).unlink(missing_ok=True)
                except Exception:
                    pass


    def is_gif(self, url: str, content_type: Optional[str] = None) -> bool:
        """
        Check if URL or content type indicates a GIF.

        Args:
            url: URL to check
            content_type: MIME type if available

        Returns:
            True if this appears to be a GIF
        """
        return looks_like_gif_url(url, content_type)
