import json, os, sys, tempfile
from PIL import Image
D = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(tempfile.gettempdir(), "exam_figure_svg", "seonggwang2")
import glob
qs = {}
for f in glob.glob(os.path.join(glob.escape(D), "ocr", "*.json")):
    for q in json.load(open(f, encoding="utf-8"))["questions"]:
        for b in q["contents"]:
            if b["type"] == "figure":
                pg = int(os.path.basename(f)[1])
                key = f"q{q['number']}" if q["number"] <= 18 else f"s{q['number']-18}"
                qs[key] = (pg, b["bbox"])
for k in (sys.argv[1:] or sorted(qs)):
    pg, bb = qs[k]
    im = Image.open(os.path.join(D, "_work", f"p{pg}_300.png"))
    w, h = im.size
    pad = 0.01
    c = im.crop((int((bb[0]-pad)*w), int((bb[1]-pad)*h), int((bb[2]+pad)*w), int((bb[3]+pad)*h)))
    r = Image.open(os.path.join(OUT, f"{k}.png")).convert("RGB")
    H = 420
    c = c.resize((int(c.width * H / c.height), H))
    r = r.resize((int(r.width * H / r.height), H))
    m = Image.new("RGB", (c.width + r.width + 20, H), "white")
    m.paste(c, (0, 0)); m.paste(r, (c.width + 20, 0))
    m.save(os.path.join(D, "_work", f"cmp_{k}.png"))
print("done")
