# -*- coding: utf-8 -*-
"""2번 <보기>: 상자 틀·제목을 그림에서 빼고(문서의 진짜 보기 표가 대신한다) 여백을 다듬는다."""
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "fig_svgs.py"
s = p.read_text(encoding="utf-8")


def rep(old, new):
    global s
    assert s.count(old) == 1, (s.count(old), old[:50])
    s = s.replace(old, new)


rep("# ── q2: <보기> 여섯 그림 — BC∥DE 인가 ───────────────────────────────────────────\n",
    "# ── q2: <보기> 여섯 그림 — BC∥DE 인가 ───────────────────────────────────────────\n"
    "# 상자 틀과 '<보기>' 제목은 그리지 않는다 — 문서 쪽에 진짜 보기 표를 만들고 그 **안에** 이 그림을\n"
    "# 넣는다(사용자 2026-10-12). ㄱ~ㅂ 표시는 2열×3행 배치를 지키려고 그림 안에 둔다.\n")
rep('_pts2["Z1"], _pts2["Z2"] = P(0, 0), P(W2, H2)\n',
    '_pts2["Z1"], _pts2["Z2"] = P(14, 34), P(W2 - 8, H2 - 6)\n')
i0 = s.index("def _q2_frame(sh):")
i1 = s.index("def _q2_over(sh):")
s = s[:i0] + s[i1:]
rep('render("q2", _pts2, _segs2, labels=_labels2, pre=_q2_frame, post=_q2_over)',
    'render("q2", _pts2, _segs2, labels=_labels2, post=_q2_over)')
p.write_text(s, encoding="utf-8")
print("patched")
