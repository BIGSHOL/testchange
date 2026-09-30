# -*- coding: utf-8 -*-
import math, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from core.figure_scene import render_figure_spec
from core.figure_quality import sanitize_svg
from core.figure_generator import _svg_to_png_bytes

u = 26.0
A = (160.0, 34.0)
D = (160.0, 34.0 + 5 * u / math.tan(math.radians(38)))
B, C = (160.0 - 5 * u, D[1]), (160.0 + 5 * u, D[1])
spec = {
    "version": 2, "theme": "exam-thin", "canvas": [320, 250],
    "points": {k: {"type": "raw", "x": v[0], "y": v[1]} for k, v in dict(A=A, B=B, C=C, D=D).items()},
    "segments": {"AB": {"points": ["A", "B"], "ticks": 2}, "AC": {"points": ["A", "C"], "ticks": 2},
                 "BC": ["B", "C"], "AD": ["A", "D"]},
    "angles": {"angA": {"vertex": "A", "points": ["B", "D"], "label": "38°"},
               "angC": {"vertex": "C", "points": ["A", "B"], "label": "y°"}},
    "dimensions": {"dimBD": {"points": ["B", "D"], "label": "5 cm", "side": "auto"},
                   "dimDC": {"points": ["D", "C"], "label": "x cm", "side": "auto"}},
    "labels": {"A": "A", "B": "B", "C": "C", "D": "D"},
}
svg = sanitize_svg(render_figure_spec(spec))
open(Path(__file__).parent / "t_q2.svg", "w", encoding="utf-8").write(svg)
open(Path(__file__).parent / "t_q2.png", "wb").write(_svg_to_png_bytes(svg, width=1000))
print(svg[:600])
