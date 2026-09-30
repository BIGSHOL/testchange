# -*- coding: utf-8 -*-
import json, os, sys
from PIL import Image
T = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = json.load(open(os.path.join(T, "crop", "crops.json"), encoding="utf-8"))
cnt = {}
for c in spec:
    p = c["page"]
    im = Image.open(os.path.join(T, "_work", f"hp{p}.png"))
    W, H = im.size
    x0, y0, x1, y1 = c["bbox"]
    m = cnt.get(p, 0) + 1
    cnt[p] = m
    c["file"] = f"p{p}_c{m}.png"
    im.crop((int(x0 * W), int(y0 * H), int(x1 * W), int(y1 * H))).save(os.path.join(T, "crop", c["file"]))
json.dump(spec, open(os.path.join(T, "crop", "crops.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("ok", len(spec))
