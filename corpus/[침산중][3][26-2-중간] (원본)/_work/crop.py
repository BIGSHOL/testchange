# -*- coding: utf-8 -*-
import json, os, sys
import fitz
from PIL import Image
D = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W = os.path.join(D, "_work")
CR = os.path.join(D, "crop")
os.makedirs(CR, exist_ok=True)
BOX = {
    1: [(1, (0.08, 0.275, 0.49, 0.535)), (2, (0.08, 0.617, 0.49, 0.755)),
        (3, (0.49, 0.135, 0.915, 0.335)), (4, (0.49, 0.385, 0.915, 0.68)),
        (5, (0.49, 0.72, 0.915, 0.845))],
    2: [(6, (0.1, 0.065, 0.5, 0.305)), (7, (0.1, 0.38, 0.5, 0.595)),
        (8, (0.1, 0.635, 0.5, 0.83)), (9, (0.5, 0.065, 0.9, 0.305)),
        (10, (0.5, 0.385, 0.9, 0.58)), (11, (0.5, 0.638, 0.9, 0.795))],
    3: [(12, (0.085, 0.058, 0.5, 0.16)), (13, (0.085, 0.26, 0.5, 0.555)),
        (14, (0.085, 0.605, 0.5, 0.83)), (15, (0.505, 0.058, 0.93, 0.265)),
        (16, (0.505, 0.345, 0.93, 0.628))],
    4: [(17, (0.085, 0.243, 0.495, 0.43)), (18, (0.085, 0.56, 0.495, 0.635)),
        (19, (0.5, 0.063, 0.93, 0.25)), (20, (0.5, 0.415, 0.93, 0.605))],
}
doc = fitz.open(os.path.join(D, "source.pdf"))
out = []
for p, items in BOX.items():
    hp = os.path.join(W, f"p{p}_300.png")
    if not os.path.exists(hp):
        doc[p - 1].get_pixmap(dpi=300).save(hp)
    im = Image.open(hp)
    w, h = im.size
    for m, (n, b) in enumerate(items, 1):
        c = im.crop((int(b[0] * w), int(b[1] * h), int(b[2] * w), int(b[3] * h)))
        c.save(os.path.join(CR, f"p{p}_c{m}.png"))
        out.append({"page": p, "number": n, "bbox": list(b), "file": f"p{p}_c{m}.png"})
json.dump(out, open(os.path.join(CR, "crops.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(out))
