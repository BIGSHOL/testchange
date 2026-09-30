# -*- coding: utf-8 -*-
import json
from pathlib import Path
from PIL import Image

HERE = Path(__file__).resolve().parents[1]
W, H = 759, 1075  # small-preview coords
BOX = {
    3: [(1, 55, 85, 382, 290), (2, 55, 385, 382, 670), (3, 55, 752, 382, 995),
        (4, 388, 85, 722, 340), (5, 388, 428, 722, 672), (6, 388, 682, 722, 930)],
    4: [(7, 48, 80, 372, 355), (8, 48, 420, 372, 695), (9, 48, 728, 372, 995),
        (10, 378, 80, 722, 380), (11, 378, 415, 722, 875)],
    5: [(12, 48, 80, 382, 362), (13, 48, 505, 382, 950), (14, 388, 80, 722, 345),
        (15, 388, 380, 722, 695), (16, 388, 725, 722, 978)],
    6: [(101, 48, 118, 372, 355), (102, 48, 392, 372, 690), (103, 48, 720, 372, 975),
        (104, 378, 80, 722, 330), (105, 378, 400, 722, 700)],
}
out = []
for page, boxes in BOX.items():
    im = Image.open(HERE / "pages" / f"p{page}_r.png")
    sx, sy = im.width / W, im.height / H
    for m, (num, x0, y0, x1, y1) in enumerate(boxes, 1):
        im.crop((int(x0 * sx), int(y0 * sy), int(x1 * sx), int(y1 * sy))).save(
            HERE / "crop" / f"p{page}_c{m}.png")
        out.append({"page": page, "number": num, "crop": f"p{page}_c{m}.png",
                    "bbox": [round(x0 / W, 4), round(y0 / H, 4), round(x1 / W, 4), round(y1 / H, 4)],
                    "page_image": f"pages/p{page}_r.png"})
(HERE / "crop" / "crops.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(len(out))
