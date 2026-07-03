"""Optional plate mockups (requires Pillow — imported lazily, so the rest of the
tool stays dependency-free). The plate is rendered legibly AND embedded in the
JPEG comment (marker ``7SPLATE:``) so an offline corroboration consumer can read it
without an OCR model; a real vision model would read the pixels instead."""
from pathlib import Path

PLATE_MARKER = "7SPLATE:"

_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",       # macOS
    "/System/Library/Fonts/Supplemental/Courier New Bold.ttf",  # macOS mono
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",     # Linux
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


def _font(size):
    from PIL import ImageFont
    for p in _FONT_CANDIDATES:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def render_plate(plate_text, out_path, note="prov – styrker plåt i text"):
    """A Swedish-plate-like card (blue EU strip + black chars on white) with the
    plate embedded in the JPEG comment. Raises ImportError if Pillow is absent."""
    from PIL import Image, ImageDraw
    w, h = 520, 150
    img = Image.new("RGB", (w, h), (245, 245, 245))
    d = ImageDraw.Draw(img)
    px0, py0, px1, py1 = 40, 40, 480, 120
    d.rounded_rectangle([px0, py0, px1, py1], radius=10, fill=(255, 255, 255),
                        outline=(20, 20, 20), width=4)
    d.rectangle([px0, py0, px0 + 34, py1], fill=(0, 51, 153))
    d.text((px0 + 8, py0 + 28), "S", font=_font(28), fill=(255, 255, 0))
    disp = plate_text[:3] + " " + plate_text[3:] if len(plate_text) == 6 else plate_text
    d.text((px0 + 70, py0 + 18), disp, font=_font(46), fill=(15, 15, 15))
    if note:
        d.text((40, 126), note, font=_font(14), fill=(120, 120, 120))
    img.save(out_path, "JPEG", quality=85, comment=(PLATE_MARKER + plate_text).encode("ascii"))
    return out_path
