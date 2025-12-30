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
from PIL import Image

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
        Extract key frames from GIF data.

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

            # Calculate which frames to extract
            if total_frames <= self.max_frames:
                # If few frames, take them all
                frame_indices = list(range(total_frames))
            else:
                # Sample frames evenly throughout the GIF
                step = max(1, total_frames // self.max_frames)
                frame_indices = list(range(0, total_frames, step))[:self.max_frames]

            # Extract frames
            for idx in frame_indices:
                try:
                    gif.seek(idx)
                    # Convert to RGB (some GIFs are in palette mode)
                    frame = gif.convert('RGB')
                    frames.append(frame.copy())
                except Exception as e:
                    logger.warning(f"Failed to extract frame {idx}: {e}")

            logger.info(f"Extracted {len(frames)} frames from GIF")

        except Exception as e:
            logger.error(f"Failed to process GIF: {e}")

        return frames

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
            llm_client: LLM client with describe_image method
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
                    description = await llm_client.describe_image(
                        f"file://{temp_path}",
                        prompt=describe_prompt
                    )

                    # Extract text from the frame
                    ocr_text = await llm_client.extract_text_from_image(f"file://{temp_path}")

                    Path(temp_path).unlink(missing_ok=True)

                    # Combine description with OCR text if found
                    if ocr_text:
                        return f"[Image: {description}]\n[Text in image: {ocr_text}]"
                    else:
                        return description
            except Exception as e:
                logger.error(f"Failed to describe single frame: {e}")
                return None

        # For multiple frames, describe each and combine
        frame_descriptions = []
        temp_files = []
        ocr_text = None

        try:
            for i, frame in enumerate(frames):
                temp_path = await self.save_frame_as_temp(frame)
                if temp_path:
                    temp_files.append(temp_path)
                    try:
                        description = await llm_client.describe_image(
                            f"file://{temp_path}",
                            prompt=f"Frame {i+1}/{len(frames)}: {describe_prompt}"
                        )
                        frame_descriptions.append(f"Frame {i+1}: {description}")
                        logger.info(f"Described frame {i+1}/{len(frames)}")

                        # Extract text from the first frame only (to avoid redundant OCR calls)
                        if i == 0 and not ocr_text:
                            try:
                                ocr_text = await llm_client.extract_text_from_image(f"file://{temp_path}")
                                if ocr_text:
                                    logger.info(f"OCR extracted text from GIF frame 1: {ocr_text[:100]}")
                            except Exception as ocr_error:
                                logger.warning(f"OCR failed on GIF frame: {ocr_error}")

                    except Exception as e:
                        logger.warning(f"Failed to describe frame {i+1}: {e}")

            # Combine descriptions
            if frame_descriptions:
                combined = f"[Animated GIF with {len(frames)} frames]\n"

                # Add OCR text if found
                if ocr_text:
                    combined += f"[Text in GIF: {ocr_text}]\n"

                combined += "\n".join(frame_descriptions)
                combined += f"\n[This appears to show: a sequence depicting {self._summarize_action(frame_descriptions)}]"

                return combined
            else:
                return None

        finally:
            # Cleanup temporary files
            for temp_file in temp_files:
                try:
                    Path(temp_file).unlink(missing_ok=True)
                except Exception:
                    pass

    def _summarize_action(self, frame_descriptions: List[str]) -> str:
        """
        Simple heuristic to summarize what's happening across frames.

        Args:
            frame_descriptions: List of frame descriptions

        Returns:
            Summary phrase
        """
        # Look for common action words
        combined_text = " ".join(frame_descriptions).lower()

        if any(word in combined_text for word in ["moving", "walking", "running", "jumping"]):
            return "movement or motion"
        elif any(word in combined_text for word in ["changing", "transforming", "becoming"]):
            return "transformation or change"
        elif any(word in combined_text for word in ["dancing", "waving", "gesturing"]):
            return "gestures or expressions"
        elif any(word in combined_text for word in ["text", "words", "typing"]):
            return "text or message animation"
        elif any(word in combined_text for word in ["rotating", "spinning", "turning"]):
            return "rotation or spinning"
        else:
            return "a sequence of events"

    def is_gif(self, url: str, content_type: Optional[str] = None) -> bool:
        """
        Check if URL or content type indicates a GIF.

        Args:
            url: URL to check
            content_type: MIME type if available

        Returns:
            True if this appears to be a GIF
        """
        if content_type:
            return "gif" in content_type.lower()

        url_lower = url.lower()
        return url_lower.endswith('.gif') or 'gif' in url_lower
