# -*- coding: utf-8 -*-
"""검수 이미지: 왼쪽 원본 크롭의 그림 영역 / 오른쪽 작도. review.py <out.png> key..."""
import json
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parents[1]
FIG = HERE / "_work" / "figpng"
crops = {c["number"]: c for c in json.loads((HERE / "crop" / "crops.json").read_text(encoding="utf-8"))}
qs = {}
for f in sorted((HERE / "ocr").glob("p*_merged.json")):
    for q in json.loads(f.read_text(encoding="utf-8"))["questions"]:
        qs[q["number"]] = q
font = ImageFont.truetype("malgun.ttf", 24)


def source(key):
    """key → (크롭 번호, figure 블록)."""
    if key.startswith("q"):
        n = int(key[1:])
        return n, next(b for b in qs[n]["contents"] if b["type"] == "figure")
    if key in ("s5a", "s5b"):
        sub = qs[20]["sub_questions"][0 if key == "s5a" else 1]
        return 105, next(b for b in sub["contents"] if b["type"] == "figure")
    n = int(key[1:])
    return 100 + n, next(b for b in qs[15 + n]["contents"] if b["type"] == "figure")


H = 420
out, keys = sys.argv[1], sys.argv[2:]
rows = []
for key in keys:
    cnum, fig = source(key)
    a = Image.open(HERE / "crop" / crops[cnum]["crop"]).convert("RGB")
    x0, y0, x1, y1 = fig["bbox"]
    a = a.crop((int(x0 * a.width), int(y0 * a.height), int(x1 * a.width), int(y1 * a.height)))
    b = Image.open(FIG / f"{key}.png").convert("RGBA")
    b = Image.alpha_composite(Image.new("RGBA", b.size, "white"), b).convert("RGB")
    a = a.resize((int(a.width * H / a.height), H))
    b = b.resize((int(b.width * H / b.height), H))
    im = Image.new("RGB", (a.width + b.width + 40, H + 40), "white")
    d = ImageDraw.Draw(im)
    d.text((5, 4), f"{key}  ORIGINAL", fill="red", font=font)
    d.text((a.width + 45, 4), "RECONSTRUCTION", fill="blue", font=font)
    im.paste(a, (0, 40))
    im.paste(b, (a.width + 40, 40))
    d.line((a.width + 20, 40, a.width + 20, H + 40), fill="#888888", width=2)
    rows.append(im)
W = max(r.width for r in rows)
M = Image.new("RGB", (W, sum(r.height for r in rows)), "white")
y = 0
for r in rows:
    M.paste(r, (0, y))
    y += r.height
M.save(HERE / "_work" / out)
print(out, M.size)
