"""Screenshot capture and compression utility.

Resizes screenshots to max 1024px wide and compresses to JPEG
to keep the base64 payload under 500KB.
"""
import base64
import io
from PIL import Image


MAX_WIDTH = 1024
MAX_SIZE_BYTES = 500_000  # 500KB


def compress_screenshot(png_bytes: bytes) -> str:
    """Compress a PNG screenshot to JPEG, resize, and return base64.

    Args:
        png_bytes: Raw PNG screenshot bytes from Playwright.

    Returns:
        Base64-encoded JPEG string, max 500KB.
    """
    img = Image.open(io.BytesIO(png_bytes))

    # Resize if wider than MAX_WIDTH
    if img.width > MAX_WIDTH:
        ratio = MAX_WIDTH / img.width
        new_height = int(img.height * ratio)
        img = img.resize((MAX_WIDTH, new_height), Image.LANCZOS)

    # Convert to RGB (JPEG doesn't support alpha)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    # Compress with decreasing quality until under size limit
    for quality in (85, 70, 50, 30):
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=quality)
        if buffer.tell() <= MAX_SIZE_BYTES:
            return base64.b64encode(buffer.getvalue()).decode("utf-8")
        buffer.seek(0)

    # Last resort: return whatever we have
    return base64.b64encode(buffer.getvalue()).decode("utf-8")
