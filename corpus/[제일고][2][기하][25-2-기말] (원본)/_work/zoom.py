# -*- coding: utf-8 -*-
"""원본 쪽 일부 확대: zoom.py <name> <page> <x0> <y0> <x1> <y1> [scale] (small 621x878 좌표)"""
import sys
from pathlib import Path
from PIL import Image

HERE = Path(__file__).resolve().parents[1]
W, H = 621, 878
name, page = sys.argv[1], int(sys.argv[2])
x0, y0, x1, y1 = map(float, sys.argv[3:7])
sc = float(sys.argv[7]) if len(sys.argv) > 7 else 1.0
im = Image.open(HERE / "pages" / f"p{page}.png")
sx, sy = im.width / W, im.height / H
c = im.crop((int(x0 * sx), int(y0 * sy), int(x1 * sx), int(y1 * sy)))
if sc != 1.0:
    c = c.resize((int(c.width * sc), int(c.height * sc)), Image.LANCZOS)
c.save(HERE / "_work" / f"z_{name}.png")
print(name, c.size)
