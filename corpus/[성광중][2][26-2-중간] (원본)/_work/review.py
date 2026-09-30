import os, sys
from PIL import Image, ImageDraw, ImageFont
D = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W = os.path.join(D, "_work")
f = ImageFont.truetype("arial.ttf", 22)
for k in (sys.argv[1:]):
    c = Image.open(os.path.join(W, f"cmp_{k}.png"))
    m = Image.new("RGB", (c.width, c.height + 34), "white")
    m.paste(c, (0, 34))
    d = ImageDraw.Draw(m)
    d.text((5, 4), "1. ORIGINAL", fill="black", font=f)
    d.text((c.width // 2 + 20, 4), "2. RECONSTRUCTION", fill="black", font=f)
    m.save(os.path.join(W, f"review_{k}.png"))
