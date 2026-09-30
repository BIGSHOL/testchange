import json, os, sys, tempfile
from PIL import Image, ImageDraw, ImageFont
here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out = os.path.join(tempfile.gettempdir(), "exam_figure_svg", "daeguil3")
fm = json.load(open(os.path.join(here, "_work", "fig_map.json"), encoding="utf-8"))
bb = {}
for n in range(1, 5):
    d = json.load(open(os.path.join(here, "ocr", f"p{n}_merged.json"), encoding="utf-8"))
    for q in d["questions"]:
        for b in q["contents"]:
            if b["type"] == "figure":
                bb[str(q["number"])] = (n, b["bbox"])
try:
    font = ImageFont.truetype("arial.ttf", 22)
except Exception:
    font = None
keys = sys.argv[1:] or list(fm)
for num in keys:
    key = fm[num]["key"]; pg, (x0, y0, x1, y1) = bb[num]
    page = Image.open(os.path.join(here, "_work", "hi", f"p{pg}.png")).convert("RGB")
    W, H = page.size; m = 0.025
    orig = page.crop((int((x0 - m) * W), int((y0 - m) * H), int((x1 + m) * W), int((y1 + m) * H)))
    r0 = Image.open(os.path.join(out, key + ".png")).convert("RGBA")
    rec = Image.new("RGB", r0.size, "white"); rec.paste(r0, mask=r0.split()[3])
    h = 520
    orig = orig.resize((int(orig.width * h / orig.height), h))
    rec = rec.resize((int(rec.width * h / rec.height), h))
    c = Image.new("RGB", (orig.width + rec.width + 30, h + 40), "white")
    c.paste(orig, (0, 40)); c.paste(rec, (orig.width + 30, 40))
    dr = ImageDraw.Draw(c)
    dr.text((5, 5), "1. ORIGINAL", fill="red", font=font)
    dr.text((orig.width + 35, 5), "2. RECONSTRUCTION " + key, fill="red", font=font)
    c.save(os.path.join(here, "_work", f"review_{key}.png"))
