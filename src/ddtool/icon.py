from __future__ import annotations

from PIL import Image

from ddtool.resources import bundled_icon_png


def create_tray_icon(size: int = 64) -> Image.Image:
    image = Image.open(bundled_icon_png()).convert("RGBA")
    if image.size != (size, size):
        image = image.resize((size, size), Image.Resampling.LANCZOS)
    return image
