# -*- coding: utf-8 -*-
from pathlib import Path
p = Path(__file__).resolve().parents[1] / "fig_svgs.py"
s = p.read_text(encoding="utf-8")
rep = [
 ('''       {"dBD": dim("B", "D", "5"), "dDC": dim("D", "C", "20")},''',
  '''       {"dBD": dim("B", "D", "5")},'''),
 ('''       post=lambda tx, ty: measured(A[0] + tx, A[1] + ty, D[0] + tx, D[1] + ty, 8, "10", FS, t=0.56))''',
  '''       # DC=20 은 두 선분(DO·OC)에 걸친 치수라 스펙 치수(한 선분 전용)로 못 건다.
       post=lambda tx, ty: measured(A[0] + tx, A[1] + ty, D[0] + tx, D[1] + ty, 8, "10", FS, t=0.56)
       + measured(D[0] + tx, D[1] + ty, C[0] + tx, C[1] + ty, 11, "20", FS))'''),
 ('''       {"dAD": dim("A", "D", "2"), "dDB": dim("D", "B", "6"), "dBC": dim("B", "C", "12")},
       post=dots(bis_pt(D, B, E, 14), bis_pt(C, A, B, 27), r=1.7))''',
  '''       {"dAD": dim("A", "D", "2"), "dDB": dim("D", "B", "6")},
       # BC=12 는 BE·EC 두 선분에 걸친 치수 — 점 E 이름표 아래로 지나게 깊게 휜다(원본 모양).
       post=lambda tx, ty: dots(bis_pt(D, B, E, 14), bis_pt(C, A, B, 27), r=1.7)(tx, ty)
       + measured(B[0] + tx, B[1] + ty, C[0] + tx, C[1] + ty, 25, "12", FS))'''),
 ('''       None,
       {"dBD": dim("B", "D", "10")},
       labels={"A": "A", "B": "B", "C": "C", "D": "D", "E": "E", "F": "F",
               "G": {"text": "G", "position": "W"}, "H": {"text": "G'", "position": "E"}},
       post=dots(G, G2))''',
  '''       labels={"A": "A", "B": "B", "C": "C", "D": "D", "E": "E", "F": "F",
               "G": {"text": "G", "position": "W"}, "H": {"text": "G'", "position": "E"}},
       # BD=10 은 네 선분에 걸친 치수 — E·C·F 이름표 아래로 지나게 깊게 휜다(원본 모양).
       post=lambda tx, ty: dots(G, G2)(tx, ty)
       + measured(B[0] + tx, B[1] + ty, Dd[0] + tx, Dd[1] + ty, 34, "10", FS))'''),
]
for a, b in rep:
    assert s.count(a) == 1, a[:60]
    s = s.replace(a, b)
p.write_text(s, encoding="utf-8")
print("patched")
