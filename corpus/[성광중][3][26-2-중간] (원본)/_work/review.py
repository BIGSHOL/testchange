import json, os, sys
from PIL import Image, ImageDraw, ImageFont
T = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import tempfile; OUT = os.path.join(tempfile.gettempdir(), "exam_figure_svg", "seonggwang3")
font = ImageFont.truetype("arial.ttf", 28)
figs = {}
for p in range(1, 5):
    d = json.load(open(os.path.join(T, "ocr", f"p{p}_merged.json"), encoding="utf-8"))
    for q in d["questions"]:
        for b in q["contents"]:
            if b["type"] == "figure":
                figs[q["number"]] = (p, b["bbox"])
keys = sys.argv[1:] or [str(k) for k in figs]
for k in keys:
    n = int(k); p, bb = figs[n]
    pg = Image.open(os.path.join(T, "_work", f"hp{p}.png"))
    W, H = pg.size
    pad = 0.01
    a = pg.crop((int((bb[0]-pad)*W), int((bb[1]-pad)*H), int((bb[2]+pad)*W), int((bb[3]+pad)*H))).convert("RGB")
    b = Image.open(os.path.join(OUT, f"q{n}.png")).convert("RGBA")
    bg = Image.new("RGB", b.size, "white"); bg.paste(b, mask=b.split()[3]); b = bg
    h = 500
    a = a.resize((int(a.width*h/a.height), h)); b = b.resize((int(b.width*h/b.height), h))
    im = Image.new("RGB", (a.width+b.width+30, h+50), "white")
    im.paste(a, (0, 50)); im.paste(b, (a.width+30, 50))
    dr = ImageDraw.Draw(im)
    dr.text((10, 10), "1. ORIGINAL", fill="black", font=font)
    dr.text((a.width+40, 10), "2. RECONSTRUCTION", fill="black", font=font)
    im.save(os.path.join(T, "_work", f"review_q{n}.png"))
print("ok")
