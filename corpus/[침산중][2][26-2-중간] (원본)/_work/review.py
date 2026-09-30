# -*- coding: utf-8 -*-
"""LEFT = 1. ORIGINAL crop, RIGHT = 2. RECONSTRUCTION → _work/review_<key>.png"""
import json, os, sys, tempfile
from PIL import Image, ImageDraw, ImageFont
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(tempfile.gettempdir(), "exam_figure_svg", "chimsan2")
crops = {str(c["number"]): c["file"] for c in json.load(open(os.path.join(HERE, "crop", "crops.json"), encoding="utf-8"))}
try:
    font = ImageFont.truetype("arial.ttf", 28)
except OSError:
    font = ImageFont.load_default()
H = 640
for k in sys.argv[1:]:
    num = k[1:] if k.startswith("q") else k
    a = Image.open(os.path.join(HERE, "crop", crops[num])).convert("RGB")
    b = Image.open(os.path.join(OUT, f"{k}.png")).convert("RGBA")
    bg = Image.new("RGB", b.size, "white"); bg.paste(b, mask=b.split()[3]); b = bg
    a = a.resize((int(a.width * H / a.height), H))
    b = b.resize((int(b.width * H / b.height), H))
    m = Image.new("RGB", (a.width + b.width + 30, H + 44), "white")
    m.paste(a, (0, 44)); m.paste(b, (a.width + 30, 44))
    d = ImageDraw.Draw(m)
    d.text((10, 6), "1. ORIGINAL", fill="black", font=font)
    d.text((a.width + 40, 6), "2. RECONSTRUCTION", fill="black", font=font)
    d.line([(a.width + 15, 0), (a.width + 15, H + 44)], fill="gray", width=2)
    m.save(os.path.join(HERE, "_work", f"review_{k}.png"))
print("ok")
