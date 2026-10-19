# -*- coding: utf-8 -*-
"""fig_map.json 생성 — 삽입 폭 = viewBox 폭 × K(mm). 모든 그림의 라벨·선 굵기가 같은 크기로 인쇄된다."""
import json
import os
import re
import runpy
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
K = 0.17
os.environ.setdefault("FIG_SVG_OUT", str(HERE / "_work" / "figpng"))
ns = runpy.run_path(str(HERE / "fig_svgs.py"), run_name="figmod")
vb = {k: tuple(map(float, re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg).groups()))
      for k, svg in ns["S"].items()}


def ent(key):
    return {"key": key, "width_mm": min(68, round(vb[key][0] * K))}


m = {"1": ent("q1"), "9": ent("q9"), "10": ent("q10"), "18": ent("s4"), "19": ent("s5")}
m["_note"] = "문항번호 기준(18 = 서술형 4, 19 = 서술형 5). 폭 = viewBox 폭 × 0.17mm, 상한 68mm."
(HERE / "_work" / "fig_map.json").write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
for k, v in m.items():
    if k != "_note":
        key = v["key"]
        print(k, key, f"viewBox {vb[key][0]:.0f}x{vb[key][1]:.0f}", "->", v["width_mm"], "mm x",
              round(v["width_mm"] * vb[key][1] / vb[key][0]), "mm")
