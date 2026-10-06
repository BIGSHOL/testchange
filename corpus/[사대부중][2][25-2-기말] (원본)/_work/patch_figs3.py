# -*- coding: utf-8 -*-
from pathlib import Path
p = Path(__file__).resolve().parents[1] / "fig_svgs.py"
s = p.read_text(encoding="utf-8")
rep = [
 ('''T4, L4, R4, F4 = P(95.3, 12), P(15, 115.2), P(187.7, 112.1), P(122.6, 148.4)''',
  '''_k4 = 1.32                                   # 원본 크기(단 폭의 절반 남짓)에 맞춘 배율
T4, L4, R4, F4 = (P(x * _k4, y * _k4) for x, y in
                  ((95.3, 12), (15, 115.2), (187.7, 112.1), (122.6, 148.4)))'''),
 ('''_tips = ((107.1, 35.3, "(가)"), (122.6, 62.5, "(나)"), (153.6, 102.2, "(다)"))
raw_svg("s4", 246, 162,''',
  '''_tips = tuple((x * _k4, y * _k4, name) for x, y, name in
              ((107.1, 35.3, "(가)"), (122.6, 62.5, "(나)"), (153.6, 102.2, "(다)")))
_lx4 = 203 * _k4
raw_svg("s4", round(_lx4 + 46), round(162 * _k4),'''),
 ('''        *[leader((203, y), (x, y), arrow=True, w=0.9, head=6.0, gap=0.0) for x, y, _ in _tips],
        *[txt(207, y + 4.5, name, FS, anc="start") for _, y, name in _tips])''',
  '''        *[leader((_lx4, y), (x, y), arrow=True, w=0.9, head=6.5, gap=0.0) for x, y, _ in _tips],
        *[txt(_lx4 + 5, y + 5.5, name, FS, anc="start") for _, y, name in _tips])'''),
]
for a, b in rep:
    assert s.count(a) == 1, a[:60]
    s = s.replace(a, b)
p.write_text(s, encoding="utf-8")
print("patched")
