# -*- coding: utf-8 -*-
"""검수 이미지: 왼쪽 '1. ORIGINAL'(원본 크롭의 그림 영역) / 오른쪽 '2. RECONSTRUCTION'."""
import json
import os
import sys
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("FIG_SVG_OUT", Path(tempfile.gettempdir()) / "exam_figure_svg" / "daeguil2"))
crops = {c["number"]: c for c in json.loads((HERE / "crop" / "crops.json").read_text(encoding="utf-8"))}
qs = {}
for f in sorted((HERE / "ocr").glob("p*_merged.json")):
    for q in json.loads(f.read_text(encoding="utf-8"))["questions"]:
        qs[q["number"]] = q
try:
    font = ImageFont.truetype("malgun.ttf", 28)
except OSError:
    font = ImageFont.load_default()

H = 520
for key in sys.argv[1:]:
    num = int(key[1:]) + (16 if key[0] == "s" else 0)
    c = crops[num if key[0] == "q" else 100 + int(key[1:])]
    a = Image.open(HERE / "crop" / c["crop"]).convert("RGB")
    fig = next(b for b in qs[num]["contents"] if b["type"] == "figure")
    x0, y0, x1, y1 = fig["bbox"]
    a = a.crop((int(x0 * a.width), int(y0 * a.height), int(x1 * a.width), int(y1 * a.height)))
    b = Image.open(OUT / f"{key}.png").convert("RGB")
    a = a.resize((int(a.width * H / a.height), H))
    b = b.resize((int(b.width * H / b.height), H))
    im = Image.new("RGB", (a.width + b.width + 30, H + 45), "white")
    d = ImageDraw.Draw(im)
    d.text((5, 5), "1. ORIGINAL", fill="black", font=font)
    d.text((a.width + 35, 5), "2. RECONSTRUCTION", fill="black", font=font)
    im.paste(a, (0, 45))
    im.paste(b, (a.width + 30, 45))
    d.line((a.width + 15, 45, a.width + 15, H + 45), fill="#888888", width=2)
    im.save(HERE / "_work" / f"review_{key}.png")
