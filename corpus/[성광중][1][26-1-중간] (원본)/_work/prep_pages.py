# -*- coding: utf-8 -*-
"""원본 PDF → pages/p{n}.png(300dpi) + _work/p{n}_small.png(75dpi). usage: prep_pages.py <pdf>"""
import sys
from pathlib import Path

import fitz

HERE = Path(__file__).resolve().parents[1]
doc = fitz.open(sys.argv[1])
for i, pg in enumerate(doc, 1):
    big = pg.get_pixmap(dpi=300)
    big.save(str(HERE / "pages" / f"p{i}.png"))
    small = pg.get_pixmap(dpi=75)
    small.save(str(HERE / "_work" / f"p{i}_small.png"))
    print(i, big.width, big.height, small.width, small.height)
