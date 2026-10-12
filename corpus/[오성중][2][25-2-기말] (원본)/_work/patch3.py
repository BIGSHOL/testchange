# -*- coding: utf-8 -*-
from pathlib import Path
p = Path(__file__).resolve().parents[1] / "fig_svgs.py"
s = p.read_text(encoding="utf-8")
rep = [
 # q2 ㅂ: A 이름표가 BD 치수 호에 걸린다 → 왼쪽으로(원본 위치)
 ('''_g6 = (A, B, C, D, E)
_pts2["Z1"], _pts2["Z2"] = P(0, 0), P(W2, H2)''',
  '''_g6 = (A, B, C, D, E)
_labels2["A6"] = {"text": "A", "position": "W"}
_pts2["Z1"], _pts2["Z2"] = P(0, 0), P(W2, H2)'''),
 # q4: 치수는 전부 삼각형 바깥(원본 위치) — 스펙 자동 배치가 AC 를 안쪽에 놓았다
 ('''       {"dAC": dim("A", "C", "75cm"), "dBC": dim("B", "C", "75cm"), "dDF": dim("D", "F", "50cm"),
        "dGI": dim("G", "I", "25cm")},
       labels={**{k: k for k in "ABCDEFGI"}, "H": {"text": "H", "position": "SW"}},
       pre=_q4_poles,
       post=lambda sh: "".join(txt(*sh((x, 72)), name, 15)
                               for x, name in ((112, "큰 깃발"), (318, "중간 깃발"), (470, "작은 깃발"))))''',
  '''       None,
       labels={**{k: k for k in "ABCDEFGI"}, "H": {"text": "H", "position": "SW"}},
       pre=_q4_poles,
       post=lambda sh: "".join(txt(*sh((x, 72)), name, 15)
                               for x, name in ((112, "큰 깃발"), (318, "중간 깃발"), (470, "작은 깃발")))
       + adim(sh(A), sh(C), -12, "75cm") + adim(sh(B), sh(C), 12, "75cm")
       + adim(sh(Dd), sh(Ff), -11, "50cm") + adim(sh(Gg), sh(Ii), -10, "25cm"))'''),
]
for a, b in rep:
    assert s.count(a) == 1, a[:60]
    s = s.replace(a, b)
p.write_text(s, encoding="utf-8")
print("patched")
