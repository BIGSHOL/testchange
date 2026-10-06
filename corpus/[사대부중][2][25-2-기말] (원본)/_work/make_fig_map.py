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


m = {str(n): ent(f"q{n}") for n in (5, 6, 7, 8, 9, 11, 12, 13, 14, 15)}
m.update({f"s{n}": ent(f"s{n}") for n in (2, 3, 4, 6)})
m["s5"] = [ent("s5a"), ent("s5b")]
m["_note"] = ("sN = 서답형 N(문항번호 15+N). s1 은 그림 없음. s5 는 소문항 (1)(2) 그림 두 개. "
              "폭 = viewBox 폭 × 0.17mm(라벨 크기 통일).")
(HERE / "_work" / "fig_map.json").write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
for k, v in m.items():
    if k != "_note":
        print(k, v)
