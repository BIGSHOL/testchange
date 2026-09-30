import sys, os, tempfile
sys.path.insert(0, r"D:\시험지 한글화"); sys.stdout.reconfigure(encoding="utf-8")
from core.figure_scene import render_figure_spec
from core.figure_quality import sanitize_svg
from core.figure_generator import _svg_to_png_bytes
spec = {"version": 2, "canvas": [260, 150],
 "points": {"A": [38, 118], "B": [218, 118], "C": [218, 28]},
 "segments": {"AB": ["A","B"], "BC": ["B","C"], "CA": ["C","A"]},
 "angles": {"angB": {"vertex": "B", "points": ["A","C"], "right": True},
            "angA": {"vertex": "A", "points": ["B","C"]}},
 "dimensions": {"dimAB": {"points": ["A","B"], "label": "2"}, "dimBC": {"points": ["B","C"], "label": "1"}},
 "regions": {"sh": {"boundary": [{"seg": ["A","B"]}, {"seg": ["B","C"]}, {"seg": ["C","A"]}], "fill": "#e0e0e0"}},
 "labels": {"A": "A", "B": "B", "C": "C"}}
svg = sanitize_svg(render_figure_spec(spec))
print(svg[:300])
open(os.path.join(tempfile.gettempdir(),"exam_figure_svg","daeguil3","_try.png"),"wb").write(_svg_to_png_bytes(svg, width=1040))
