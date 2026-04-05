"""Convert icon.svg → icon.ico (multi-resolution) for PyInstaller bundling.

Run this once before building:
    python build_icon.py

Requires: cairosvg, Pillow
    pip install cairosvg Pillow
"""

import io
import os
import sys

try:
    import cairosvg
    from PIL import Image
except ImportError:
    print("Install dependencies: pip install cairosvg Pillow")
    sys.exit(1)

HERE = os.path.dirname(os.path.abspath(__file__))
SVG_PATH = os.path.join(HERE, "src", "icon.svg")
ICO_PATH = os.path.join(HERE, "src", "icon.ico")

# Render SVG → PNG at 256×256
png_bytes = cairosvg.svg2png(url=SVG_PATH, output_width=256, output_height=256)
img_256 = Image.open(io.BytesIO(png_bytes)).convert("RGBA")

# Create multiple sizes for ICO
sizes = [16, 24, 32, 48, 64, 128, 256]
images = [img_256.resize((s, s), Image.LANCZOS) for s in sizes]

# Save as ICO with all sizes
images[0].save(
    ICO_PATH,
    format="ICO",
    append_images=images[1:],
    sizes=[(s, s) for s in sizes],
)

print(f"Icon saved: {ICO_PATH}")
