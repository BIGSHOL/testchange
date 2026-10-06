# -*- coding: utf-8 -*-
"""세션 비전으로 판독한 문항 bbox → crop/p{n}_c{m}.png + crops.json (Gemini 검출 호출 없음)."""
import json
from pathlib import Path
from PIL import Image

HERE = Path(__file__).resolve().parents[1]
W, H = 759, 1075  # small-preview(75dpi) 좌표
# (문항번호, x0, y0, x1, y1) — 서답형은 100+N
BOX = {
    1: [(1, 52, 312, 382, 430), (2, 52, 540, 382, 632), (3, 52, 748, 382, 870),
        (4, 384, 200, 728, 330), (5, 384, 385, 728, 632), (6, 384, 698, 728, 932)],
    2: [(7, 52, 90, 378, 305), (8, 52, 376, 378, 606), (9, 52, 672, 378, 928),
        (10, 380, 90, 728, 240), (11, 380, 306, 728, 550), (12, 380, 622, 728, 862)],
    3: [(13, 52, 96, 378, 290), (14, 52, 356, 378, 622), (15, 52, 684, 378, 952),
        (101, 382, 96, 728, 172), (102, 382, 290, 728, 478), (103, 382, 604, 728, 808)],
    4: [(104, 46, 82, 370, 288), (105, 46, 410, 370, 824), (106, 372, 82, 728, 285)],
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
