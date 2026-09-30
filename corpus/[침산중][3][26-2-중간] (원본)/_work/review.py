# -*- coding: utf-8 -*-
"""원본 그림 크롭 ↔ 재구성 PNG 나란히(도형편집기 리뷰 루프)."""
import glob, json, os, sys, tempfile
from PIL import Image, ImageDraw, ImageFont
D = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W = os.path.join(D, "_work")
OUT = os.environ.get("FIG_SVG_OUT", os.path.join(tempfile.gettempdir(), "exam_figure_svg", "chimsan3"))
KEY = {1: "q1", 3: "q3", 4: "q4", 6: "q6", 7: "q7", 9: "q9", 10: "q10", 13: "q13",
       15: "q15", 16: "q16", 17: "s1", 19: "s3", 20: "s4"}
src = {}
for fp in sorted(glob.glob(os.path.join(glob.escape(D), "ocr", "p*_merged.json"))):
    pg = int(os.path.basename(fp)[1])
    for q in json.load(open(fp, encoding="utf-8"))["questions"]:
        for b in q["contents"]:
            if b["type"] == "figure":
                src[KEY[q["number"]]] = (pg, b["bbox"])
font = ImageFont.truetype("malgun.ttf", 28)
only = sys.argv[1:]
for key, (pg, bb) in src.items():
    if only and key not in only:
        continue
    im = Image.open(os.path.join(W, f"p{pg}_300.png")).convert("RGB")
    w, h = im.size
    pad = 0.012
    o = im.crop((int((bb[0] - pad) * w), int((bb[1] - pad) * h), int((bb[2] + pad) * w), int((bb[3] + pad) * h)))
    r0 = Image.open(os.path.join(OUT, f"{key}.png")).convert("RGBA")
    r = Image.new("RGB", r0.size, "white"); r.paste(r0, mask=r0.split()[3])
    H = 600
    o = o.resize((int(o.width * H / o.height), H))
    r = r.resize((int(r.width * H / r.height), H))
    c = Image.new("RGB", (o.width + r.width + 30, H + 50), "white")
    c.paste(o, (0, 50)); c.paste(r, (o.width + 30, 50))
    d = ImageDraw.Draw(c)
    d.text((10, 8), "1. ORIGINAL", fill="black", font=font)
    d.text((o.width + 40, 8), "2. RECONSTRUCTION", fill="black", font=font)
    c.save(os.path.join(W, f"review_{key}.png"))
print("ok")
