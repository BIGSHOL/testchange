# -*- coding: utf-8 -*-
"""세션 비전으로 판독한 문항 bbox → crop/p{n}_c{m}.png + crops.json (Gemini 검출 호출 없음)."""
import json
from pathlib import Path
from PIL import Image

HERE = Path(__file__).resolve().parents[1]
W, H = 621, 878  # small-preview(75dpi) 좌표
# (문항번호, x0, y0, x1, y1) — 서술형은 15~20. p1 은 표지.
BOX = {
    2: [(1, 30, 60, 312, 250), (2, 30, 312, 312, 450), (3, 30, 562, 312, 626),
        (4, 312, 60, 600, 140), (5, 312, 302, 600, 352), (6, 312, 556, 600, 598)],
    3: [(7, 30, 60, 312, 112), (8, 30, 298, 312, 356), (9, 30, 522, 312, 664),
        (10, 312, 60, 600, 332), (11, 312, 522, 600, 600)],
    4: [(12, 30, 60, 312, 112), (13, 30, 298, 312, 356), (14, 30, 522, 312, 582),
        (15, 312, 60, 600, 146), (16, 312, 298, 600, 346), (17, 312, 522, 600, 584)],
    5: [(18, 30, 62, 312, 252), (19, 30, 442, 312, 672), (20, 312, 62, 600, 142)],
}
out = []
for page, boxes in BOX.items():
    im = Image.open(HERE / "pages" / f"p{page}.png")
    sx, sy = im.width / W, im.height / H
    for m, (num, x0, y0, x1, y1) in enumerate(boxes, 1):
        im.crop((int(x0 * sx), int(y0 * sy), int(x1 * sx), int(y1 * sy))).save(
            HERE / "crop" / f"p{page}_c{m}.png")
        out.append({"page": page, "number": num, "crop": f"p{page}_c{m}.png",
                    "bbox": [round(x0 / W, 4), round(y0 / H, 4), round(x1 / W, 4), round(y1 / H, 4)],
                    "page_image": f"pages/p{page}.png"})
(HERE / "crop" / "crops.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(len(out))
