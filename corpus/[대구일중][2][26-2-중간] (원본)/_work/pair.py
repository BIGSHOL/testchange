# -*- coding: utf-8 -*-
"""원본 크롭 ↔ 작도 PNG 나란히(검수용)."""
import json
import os
import sys
import tempfile
from pathlib import Path
from PIL import Image

HERE = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("FIG_SVG_OUT", Path(tempfile.gettempdir()) / "exam_figure_svg" / "daeguil2"))
crops = json.loads((HERE / "crop" / "crops.json").read_text(encoding="utf-8"))
bynum = {c["number"]: c for c in crops}
for key in sys.argv[1:]:
    num = int(key[1:]) + (100 if key[0] == "s" else 0)
    c = bynum[num]
    a = Image.open(HERE / "crop" / c["crop"]).convert("RGB")
    b = Image.open(OUT / f"{key}.png").convert("RGB")
    H = 700
    a = a.resize((int(a.width * H / a.height), H))
    b = b.resize((int(b.width * H / b.height * 0.8), int(H * 0.8)))
    im = Image.new("RGB", (a.width + b.width + 20, H), "white")
    im.paste(a, (0, 0))
    im.paste(b, (a.width + 20, 60))
    im.save(HERE / "_work" / f"pair_{key}.png")
