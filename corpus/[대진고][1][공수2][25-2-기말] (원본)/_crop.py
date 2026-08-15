# -*- coding: utf-8 -*-
"""페이지 PDF 에서 지정 영역을 고해상도로 잘라 낸다. 좌표는 0~1 상대값."""
import sys, os
import pymupdf
from PIL import Image

SRC = r'N:\개인\기출\기출작업\200차\[대진고][1][공수2][25-2-기말][미래엔] (원본).pdf'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'view')
os.makedirs(OUT, exist_ok=True)

def crop(page, x0, y0, x1, y1, name, dpi=400, gray=False):
    d = pymupdf.open(SRC)
    p = d[page-1]
    m = pymupdf.Matrix(dpi/72, dpi/72)
    pix = p.get_pixmap(matrix=m)
    im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples[:pix.width*pix.height*3]) \
         if pix.n >= 3 else Image.frombytes("L", (pix.width, pix.height), pix.samples)
    W, H = im.size
    box = (int(x0*W), int(y0*H), int(x1*W), int(y1*H))
    c = im.crop(box)
    if gray:
        c = c.convert("L")
    fp = os.path.join(OUT, name + ".png")
    c.save(fp)
    d.close()
    print(fp, c.size)
    return fp

if __name__ == "__main__":
    a = sys.argv[1:]
    crop(int(a[0]), float(a[1]), float(a[2]), float(a[3]), float(a[4]), a[5],
         int(a[6]) if len(a) > 6 else 400)
