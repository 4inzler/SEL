"""
OCR text extraction for SEL Desktop
Uses Tesseract OCR to read text from screen regions
"""
import pyautogui
from PIL import Image
import io
try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    print("⚠️  pytesseract not installed. OCR features disabled.")
    print("   Install with: pip install pytesseract")
    print("   Also install Tesseract: https://github.com/tesseract-ocr/tesseract")

def check_tesseract():
    """Check if Tesseract is available"""
    if not TESSERACT_AVAILABLE:
        return False, "pytesseract module not installed"

    try:
        pytesseract.get_tesseract_version()
        return True, "Tesseract ready"
    except Exception as e:
        return False, f"Tesseract not found: {e}"

def ocr_full_screen() -> str:
    """
    Read all text from the entire screen
    Returns extracted text or error message
    """
    if not TESSERACT_AVAILABLE:
        return "Error: pytesseract not installed. Install with: pip install pytesseract"

    try:
        # Capture full screen
        screenshot = pyautogui.screenshot()

        # Extract text
        text = pytesseract.image_to_string(screenshot)

        if not text.strip():
            return "No text detected on screen"

        return f"Extracted text ({len(text)} chars):\n{text}"

    except Exception as e:
        return f"OCR error: {e}"

def ocr_region(x: int, y: int, width: int, height: int) -> str:
    """
    Read text from a specific screen region

    Args:
        x, y: Top-left corner coordinates
        width, height: Region dimensions

    Returns:
        Extracted text or error message
    """
    if not TESSERACT_AVAILABLE:
        return "Error: pytesseract not installed"

    try:
        # Capture region
        screenshot = pyautogui.screenshot(region=(x, y, width, height))

        # Extract text
        text = pytesseract.image_to_string(screenshot)

        if not text.strip():
            return f"No text detected in region ({x},{y},{width},{height})"

        return f"Extracted from region: {text.strip()}"

    except Exception as e:
        return f"OCR region error: {e}"

def ocr_find_text(search_text: str) -> dict:
    """
    Find text on screen and return its coordinates

    Args:
        search_text: Text to search for

    Returns:
        Dictionary with found status and coordinates
    """
    if not TESSERACT_AVAILABLE:
        return {"found": False, "error": "pytesseract not installed"}

    try:
        # Capture screen
        screenshot = pyautogui.screenshot()

        # Get text with bounding boxes
        data = pytesseract.image_to_data(screenshot, output_type=pytesseract.Output.DICT)

        # Search for text
        search_lower = search_text.lower()
        found_items = []

        for i, text in enumerate(data['text']):
            if text and search_lower in text.lower():
                x = data['left'][i]
                y = data['top'][i]
                w = data['width'][i]
                h = data['height'][i]
                confidence = data['conf'][i]

                found_items.append({
                    "text": text,
                    "x": x + w // 2,  # Center point
                    "y": y + h // 2,
                    "width": w,
                    "height": h,
                    "confidence": confidence
                })

        if found_items:
            # Return best match (highest confidence)
            best = max(found_items, key=lambda x: x['confidence'])
            return {
                "found": True,
                "text": best['text'],
                "x": best['x'],
                "y": best['y'],
                "width": best['width'],
                "height": best['height'],
                "confidence": best['confidence'],
                "total_matches": len(found_items)
            }
        else:
            return {
                "found": False,
                "error": f"Text '{search_text}' not found on screen"
            }

    except Exception as e:
        return {
            "found": False,
            "error": f"OCR search error: {e}"
        }

def ocr_get_screen_text_data() -> dict:
    """
    Get all text on screen with positions (for advanced use)

    Returns:
        Dictionary with all text elements and positions
    """
    if not TESSERACT_AVAILABLE:
        return {"error": "pytesseract not installed"}

    try:
        screenshot = pyautogui.screenshot()
        data = pytesseract.image_to_data(screenshot, output_type=pytesseract.Output.DICT)

        # Filter out empty text
        text_elements = []
        for i, text in enumerate(data['text']):
            if text.strip():
                text_elements.append({
                    "text": text,
                    "x": data['left'][i] + data['width'][i] // 2,
                    "y": data['top'][i] + data['height'][i] // 2,
                    "width": data['width'][i],
                    "height": data['height'][i],
                    "confidence": data['conf'][i]
                })

        return {
            "success": True,
            "elements": text_elements,
            "total": len(text_elements)
        }

    except Exception as e:
        return {"error": f"OCR data error: {e}"}
