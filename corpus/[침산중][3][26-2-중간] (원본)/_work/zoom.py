# -*- coding: utf-8 -*-
import os, sys
import fitz
D = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
doc = fitz.open(os.path.join(D, "source.pdf"))
p, x0, y0, x1, y1, name = int(sys.argv[1]), *map(float, sys.argv[2:6]), sys.argv[6]
pg = doc[p - 1]
r = pg.rect
clip = fitz.Rect(r.x0 + x0 * r.width, r.y0 + y0 * r.height, r.x0 + x1 * r.width, r.y0 + y1 * r.height)
pg.get_pixmap(dpi=int(sys.argv[7]) if len(sys.argv) > 7 else 400, clip=clip).save(os.path.join(D, "_work", name + ".png"))
