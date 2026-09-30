# -*- coding: utf-8 -*-
import json, os, sys, tempfile
from PIL import Image
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(tempfile.gettempdir(), "exam_figure_svg", "chimsan2")
crops = {str(c["number"]): c["file"] for c in json.load(open(os.path.join(HERE, "crop", "crops.json"), encoding="utf-8"))}
keys = sys.argv[1:]
for k in keys:
    num = k[1:] if k.startswith("q") else k
    a = Image.open(os.path.join(HERE, "crop", crops[num])).convert("RGB")
    b = Image.open(os.path.join(OUT, f"{k}.png")).convert("RGBA")
    bg = Image.new("RGB", b.size, "white"); bg.paste(b, mask=b.split()[3]); b = bg
    h = 700
    a = a.resize((int(a.width * h / a.height), h))
    b = b.resize((int(b.width * h * 0.8 / b.height), int(h * 0.8)))
    m = Image.new("RGB", (a.width + b.width + 20, h), "white")
    m.paste(a, (0, 0)); m.paste(b, (a.width + 20, 60))
    m.save(os.path.join(HERE, "_work", f"cmp_{k}.png"))
print("ok")
