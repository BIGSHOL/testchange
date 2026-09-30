# usage: python zoom.py page x0 y0 x1 y1 out  (fractions of page)
import sys, os
from PIL import Image
T = os.path.dirname(os.path.abspath(__file__))
p, x0, y0, x1, y1, out = sys.argv[1:7]
im = Image.open(os.path.join(T, f"hp{p}.png"))
W, H = im.size
im.crop((int(float(x0) * W), int(float(y0) * H), int(float(x1) * W), int(float(y1) * H))).save(os.path.join(T, out))
