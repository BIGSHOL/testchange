# -*- coding: utf-8 -*-
"""작도 PNG 를 흰 바탕에 나란히. usage: montage.py <out.png> <key> ..."""
import os
import sys
from PIL import Image

d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figpng")
H = int(os.environ.get("MH", "330"))
ims = []
for k in sys.argv[2:]:
    im = Image.open(os.path.join(d, f"{k}.png")).convert("RGBA")
    bg = Image.new("RGBA", im.size, "white")
    im = Image.alpha_composite(bg, im).convert("RGB")
    ims.append(im.resize((int(im.width * H / im.height), H), Image.LANCZOS))
W = sum(im.width for im in ims) + 24 * len(ims)
M = Image.new("RGB", (W, H), "#dddddd")
x = 0
for im in ims:
    M.paste(im, (x, 0))
    x += im.width + 24
M.save(sys.argv[1])
print(M.size)
