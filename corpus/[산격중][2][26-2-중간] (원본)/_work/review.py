"""도형편집기 검토용 나란히 보기: 왼쪽 1. ORIGINAL(원본 크롭) / 오른쪽 2. RECONSTRUCTION."""
import json
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parents[1]
OUT = Path(tempfile.gettempdir()) / "exam_figure_svg" / "sangyeok2"
crops = json.load(open(HERE / "crop" / "crops.json", encoding="utf-8"))
key2crop, idx = {}, {}
for c in crops:
    idx[c["page"]] = idx.get(c["page"], 0) + 1
    n = c["number"]
    key2crop[f"q{n}" if isinstance(n, int) else n] = HERE / "crop" / f"p{c['page']}_c{idx[c['page']]}.png"
try:
    font = ImageFont.truetype("arial.ttf", 28)
except OSError:
    font = ImageFont.load_default()
for k in sys.argv[1:]:
    a = Image.open(key2crop[k]).convert("RGB")
    b = Image.open(OUT / f"{k}.png").convert("RGBA")
    bg = Image.new("RGB", b.size, "white")
    bg.paste(b, mask=b.split()[3])
    h = 640
    a = a.resize((int(a.width * h / a.height), h))
    b = bg.resize((int(bg.width * h / bg.height), h))
    m = Image.new("RGB", (a.width + b.width + 30, h + 44), "white")
    m.paste(a, (0, 44))
    m.paste(b, (a.width + 30, 44))
    d = ImageDraw.Draw(m)
    d.text((8, 6), "1. ORIGINAL", fill="black", font=font)
    d.text((a.width + 38, 6), "2. RECONSTRUCTION", fill="black", font=font)
    d.line((a.width + 15, 0, a.width + 15, h + 44), fill="gray", width=2)
    m.save(HERE / "_work" / f"review_{k}.png")
print("ok")
