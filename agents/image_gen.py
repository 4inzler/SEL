"""
Image Generation Agent for SEL

Uses SwarmUI (Stable Diffusion) to generate images.
SEL can use this when users request images or when it wants to illustrate something.

Environment variables:
- SWARMUI_URL: SwarmUI API endpoint (default: http://localhost:7801)
- SWARMUI_API_KEY: Optional API key for SwarmUI

Usage examples:
- "generate an image of a sunset over the ocean"
- "create a picture of a cat wearing sunglasses"
- "make me an illustration of a cyberpunk city"
"""

import os
import httpx
import base64
from typing import Optional

DESCRIPTION = "Generate images using AI (Stable Diffusion via SwarmUI)"

# Configuration
SWARMUI_URL = os.environ.get("SWARMUI_URL", "http://localhost:7801")
SWARMUI_API_KEY = os.environ.get("SWARMUI_API_KEY", "")


def _clean_prompt(text: str) -> str:
    """Extract and clean the image prompt from user request"""
    # Remove common request phrases
    text = text.lower()
    for prefix in [
        "generate an image of ",
        "create an image of ",
        "make an image of ",
        "generate ",
        "create ",
        "make ",
        "draw ",
        "image of ",
        "picture of ",
        "illustration of ",
    ]:
        if text.startswith(prefix):
            text = text[len(prefix):]
            break

    return text.strip()


def _generate_image(prompt: str, negative_prompt: str = "", steps: int = 20, cfg_scale: float = 7.0) -> dict:
    """
    Generate image using SwarmUI API

    Args:
        prompt: Image description
        negative_prompt: What to avoid in image
        steps: Number of diffusion steps
        cfg_scale: Prompt adherence strength

    Returns:
        Result dict with image data or error
    """
    try:
        # SwarmUI API endpoint
        api_url = f"{SWARMUI_URL}/API/GenerateText2Image"

        # Request payload
        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt or "blurry, low quality, distorted, ugly, watermark",
            "steps": steps,
            "cfg_scale": cfg_scale,
            "width": 512,
            "height": 512,
            "seed": -1,  # Random seed
            "sampler": "DPM++ 2M Karras",
        }

        # Add API key if configured
        headers = {}
        if SWARMUI_API_KEY:
            headers["Authorization"] = f"Bearer {SWARMUI_API_KEY}"

        # Make request
        with httpx.Client(timeout=120.0) as client:
            response = client.post(api_url, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()

        # Check for image data
        if "images" in result and len(result["images"]) > 0:
            image_b64 = result["images"][0]
            return {
                "success": True,
                "image_data": image_b64,
                "prompt": prompt,
                "format": "base64"
            }
        else:
            return {
                "success": False,
                "error": "No image generated (empty response)"
            }

    except httpx.HTTPError as e:
        return {
            "success": False,
            "error": f"HTTP error: {e}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Generation error: {e}"
        }


def run(query: str, **kwargs) -> str:
    """
    Generate an image based on text description

    Examples:
        "a sunset over the ocean" -> Generates beach sunset
        "cat wearing sunglasses in cyberpunk city" -> Generates cool cat
        "abstract art with vibrant colors" -> Generates abstract image
    """
    # Clean the prompt
    prompt = _clean_prompt(query)

    if not prompt or len(prompt) < 3:
        return "❌ Please provide a description of what you want me to generate."

    # Check if SwarmUI is accessible
    try:
        with httpx.Client(timeout=5.0) as client:
            health_check = client.get(f"{SWARMUI_URL}/API/ListModels")
            if health_check.status_code != 200:
                return (
                    f"❌ SwarmUI not responding at {SWARMUI_URL}\n"
                    f"Make sure SwarmUI is running and accessible.\n"
                    f"Set SWARMUI_URL environment variable if using a different endpoint."
                )
    except Exception as e:
        return (
            f"❌ Cannot connect to SwarmUI at {SWARMUI_URL}\n"
            f"Error: {e}\n"
            f"Make sure SwarmUI is running and the URL is correct."
        )

    # Generate the image
    result = _generate_image(prompt)

    if not result["success"]:
        return f"❌ Image generation failed: {result['error']}"

    # For Discord bot, we need to save the image and return the path
    # Discord.py will handle uploading the file
    try:
        import tempfile
        import uuid

        # Decode base64 image
        image_data = base64.b64decode(result["image_data"])

        # Save to temporary file
        temp_dir = tempfile.gettempdir()
        filename = f"sel_generated_{uuid.uuid4().hex[:8]}.png"
        filepath = os.path.join(temp_dir, filename)

        with open(filepath, "wb") as f:
            f.write(image_data)

        return f"IMAGE:{filepath}\n\n✨ Generated image: {prompt}"

    except Exception as e:
        return f"❌ Failed to save image: {e}"


def get_image_path_from_response(response: str) -> Optional[str]:
    """
    Extract image file path from agent response

    Args:
        response: Agent response string

    Returns:
        File path if found, None otherwise
    """
    if response.startswith("IMAGE:"):
        lines = response.split("\n")
        if len(lines) > 0:
            return lines[0][6:].strip()  # Remove "IMAGE:" prefix
    return None
