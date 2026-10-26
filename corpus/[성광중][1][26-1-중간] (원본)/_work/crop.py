# -*- coding: utf-8 -*-
"""세션 비전으로 판독한 문항 bbox → crop/p{n}_c{m}.png + crops.json (Gemini 검출 호출 없음)."""
import json
from pathlib import Path
from PIL import Image

HERE = Path(__file__).resolve().parents[1]
W, H = 670, 893  # small-preview(75dpi) 좌표
# (문항번호, x0, y0, x1, y1) — 서술형은 100+N.
BOX = {
    1: [(1, 25, 210, 325, 340), (2, 25, 425, 325, 492), (3, 25, 595, 325, 702),
        (4, 320, 138, 625, 205), (5, 320, 308, 625, 412), (6, 320, 545, 625, 702)],
    2: [(7, 68, 62, 325, 192), (8, 68, 222, 325, 402), (9, 68, 408, 325, 628),
        (10, 325, 58, 625, 348), (11, 325, 450, 625, 652)],
    3: [(12, 58, 92, 325, 262), (13, 58, 340, 325, 472), (14, 58, 560, 325, 662),
        (15, 325, 92, 625, 398), (16, 325, 498, 625, 672)],
    4: [(17, 58, 58, 325, 148), (18, 58, 262, 325, 362),
        (101, 58, 540, 325, 602), (102, 320, 52, 625, 122), (103, 320, 398, 625, 448)],
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
