import sys, os, tempfile
from PIL import Image, ImageDraw
out = os.path.join(tempfile.gettempdir(), "exam_figure_svg", "daeguil3")
keys = sys.argv[2:]
ims = []
for k in keys:
    im0 = Image.open(os.path.join(out, k + ".png")).convert("RGBA"); im = Image.new("RGB", im0.size, "white"); im.paste(im0, mask=im0.split()[3])
    im.thumbnail((520, 520))
    c = Image.new("RGB", (540, 540), "white"); c.paste(im, (10, 10))
    ImageDraw.Draw(c).rectangle([0,0,539,539], outline="red")
    ImageDraw.Draw(c).text((12, 520), k, fill="red")
    ims.append(c)
cols = 3
rows = (len(ims)+cols-1)//cols
M = Image.new("RGB", (540*cols, 540*rows), "white")
for i, c in enumerate(ims): M.paste(c, ((i%cols)*540, (i//cols)*540))
M.save(sys.argv[1])
