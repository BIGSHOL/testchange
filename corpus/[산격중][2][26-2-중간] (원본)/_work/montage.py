import json, os, sys, tempfile
from pathlib import Path
from PIL import Image
HERE = Path(__file__).resolve().parents[1]
OUT = Path(tempfile.gettempdir()) / "exam_figure_svg" / "sangyeok2"
crops = json.load(open(HERE / "crop" / "crops.json", encoding="utf-8"))
key2crop = {}
idx = {}
for c in crops:
    idx[c["page"]] = idx.get(c["page"], 0) + 1
    n = c["number"]
    k = f"q{n}" if isinstance(n, int) else n
    key2crop[k] = HERE / "crop" / f"p{c['page']}_c{idx[c['page']]}.png"
keys = sys.argv[1:]
for k in keys:
    a = Image.open(key2crop[k]).convert("RGB")
    b = Image.open(OUT / f"{k}.png").convert("RGBA")
    bg = Image.new("RGB", b.size, "white"); bg.paste(b, mask=b.split()[3]); b = bg
    h = 700
    a = a.resize((int(a.width * h / a.height), h))
    b = b.resize((int(b.width * h * 0.8 / b.height), int(h * 0.8)))
    m = Image.new("RGB", (a.width + b.width + 20, h), "white")
    m.paste(a, (0, 0)); m.paste(b, (a.width + 20, 50))
    m.save(HERE / "_work" / f"cmp_{k}.png")
print("ok")
