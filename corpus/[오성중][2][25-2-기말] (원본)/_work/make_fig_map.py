# -*- coding: utf-8 -*-
"""fig_map.json 생성 — 삽입 폭 = viewBox 폭 × K(mm). 모든 그림의 라벨·선 굵기가 같은 크기로 인쇄된다."""
import json
import os
import re
import runpy
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
K = 0.17
# q4 = 단 폭(약 104mm)을 거의 채우는 가로 배열 그림. q2 = <보기> 표 **안**에 들어가는 그림 —
# 5×5 보기 표의 내용 칸 안쪽 폭이 93.8mm(칸 27609 − 좌우 여백 510×2 HWPUNIT)라 92mm 로 맞춘다.
WIDE = {"q2": 92, "q4": 96}
os.environ.setdefault("FIG_SVG_OUT", str(HERE / "_work" / "figpng"))
ns = runpy.run_path(str(HERE / "fig_svgs.py"), run_name="figmod")
vb = {k: tuple(map(float, re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg).groups()))
      for k, svg in ns["S"].items()}


def ent(key):
    return {"key": key, "width_mm": min(WIDE.get(key, 68), round(vb[key][0] * K))}


m = {str(n): ent(f"q{n}") for n in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 15)}
m.update({f"s{n}": ent(f"s{n}") for n in (1, 2, 3)})
m["_note"] = ("sN = 서술형 N(문항번호 16+N). 서술형 4·5 는 그림 없음. "
              "폭 = viewBox 폭 × 0.17mm(라벨 크기 통일), q4 는 단 폭 상한 96mm, q2 는 보기 표 안쪽 폭 92mm.")
(HERE / "_work" / "fig_map.json").write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
for k, v in m.items():
    if k != "_note":
        key = v["key"]
        print(k, key, f"viewBox {vb[key][0]:.0f}x{vb[key][1]:.0f}", "->", v["width_mm"], "mm x",
              round(v["width_mm"] * vb[key][1] / vb[key][0]), "mm")
