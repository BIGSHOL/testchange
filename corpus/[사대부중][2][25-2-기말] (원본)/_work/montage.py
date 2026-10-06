# -*- coding: utf-8 -*-
"""작도 PNG 몽타주: montage.py <out.png> key1 key2 ..."""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parents[1]
FIG = HERE / "_work" / "figpng"
out, keys = sys.argv[1], sys.argv[2:]
cell_w, cell_h, cols = 520, 400, 4
font = ImageFont.truetype("malgun.ttf", 22)
rows = (len(keys) + cols - 1) // cols
M = Image.new("RGB", (cols * cell_w, rows * cell_h), "white")
d = ImageDraw.Draw(M)
for i, k in enumerate(keys):
    im = Image.open(FIG / f"{k}.png").convert("RGBA")
    bg = Image.new("RGBA", im.size, "white")
    im = Image.alpha_composite(bg, im).convert("RGB")
    s = min((cell_w - 20) / im.width, (cell_h - 40) / im.height)
    im = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
    x, y = (i % cols) * cell_w, (i // cols) * cell_h
    M.paste(im, (x + 10, y + 34))
    d.text((x + 8, y + 4), k, fill="red", font=font)
    d.rectangle((x, y, x + cell_w - 1, y + cell_h - 1), outline="#cccccc")
M.save(HERE / "_work" / out)
print(out, M.size)
