# -*- coding: utf-8 -*-
"""세션 비전으로 판독한 문항 bbox → crop/p{n}_c{m}.png + crops.json (Gemini 검출 호출 없음)."""
import json
from pathlib import Path
from PIL import Image

HERE = Path(__file__).resolve().parents[1]
W, H = 760, 1077  # small-preview(75dpi) 좌표
# (문항번호, x0, y0, x1, y1) — 서술형은 100+N. p1 은 표지.
BOX = {
    2: [(1, 45, 198, 378, 470), (2, 45, 540, 378, 988), (3, 380, 198, 728, 482), (4, 380, 510, 728, 948)],
    3: [(5, 40, 60, 378, 338), (6, 40, 362, 378, 702), (7, 40, 726, 378, 1032),
        (8, 380, 60, 728, 348), (9, 380, 376, 728, 698), (10, 380, 710, 728, 1002)],
    4: [(11, 38, 66, 375, 338), (12, 38, 398, 375, 702), (13, 38, 772, 375, 942),
        (14, 378, 66, 728, 292), (15, 378, 298, 728, 628), (16, 378, 638, 728, 912)],
    5: [(101, 50, 138, 385, 352), (102, 50, 412, 385, 612), (103, 50, 708, 385, 892),
        (104, 388, 66, 728, 192), (105, 388, 508, 728, 592)],
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
