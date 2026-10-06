# -*- coding: utf-8 -*-
from pathlib import Path
p = Path(__file__).resolve().parents[1] / "fig_svgs.py"
s = p.read_text(encoding="utf-8")
rep = [
 # q6: I 이름표는 엔진 자동 배치(SW 고정은 halo 가 AD·EI 를 지웠다)
 ('''               "I": {"text": "I", "position": "SW"}},
       post=dots(I))

# ── q7''', '''               "I": "I"},
       post=dots(I))

# ── q7'''),
 # q9: AB 치수는 O 이름표 바깥으로(원본도 깊게 휜다), 라벨은 A 쪽으로 비켜 둔다
 ('''for p, q, o, t in ((A, B, 13, "20"), (B, C, 11, "16"), (A, C, -9, "12"))))''',
  '''for p, q, o, t in ((B, C, 11, "16"), (A, C, -9, "12")))
       + measured(A[0] + tx, A[1] + ty, B[0] + tx, B[1] + ty, 22, "20", FS, t=0.36))'''),
 # q11: 작은 사각형이 너무 작아 100° 라벨 halo 가 변을 지웠다 → 척도·라벨 거리 키움
 ('''u = 28.0
_C, _D, _B = (3.0, 0.0), (2.53, 2.06), (0.0, 0.0)''', '''u = 33.0
_C, _D, _B = (3.0, 0.0), (2.53, 2.06), (0.0, 0.0)'''),
 ('''    return P(20 + p[0] * u, 200 - p[1] * u)''', '''    return P(20 + p[0] * u, 220 - p[1] * u)'''),
 ('''    return P(20 + 3 * u + 64 + 2 * (3 - p[0]) * u, 200 - 2 * p[1] * u)''',
  '''    return P(20 + 3 * u + 60 + 2 * (3 - p[0]) * u, 220 - 2 * p[1] * u)'''),
 ('''{"angD": ang("D", "A", "C", "100°")},''', '''{"angD": ang("D", "A", "C", "100°", radius=13, label_distance=33)},'''),
 # q13: 지면 폭에 맞게 축소
 ('''k13, s13 = 16.0, 17.0 ''', '''k13, s13 = 13.0, 13.8 '''),
 ('''yl, ym, yn = 28.0, 28.0 + 7 * k13, 28.0 + 12 * k13''', '''yl, ym, yn = 26.0, 26.0 + 7 * k13, 26.0 + 12 * k13'''),
 ('''T1, T2, T3 = _tr(128, 7, -1), _tr(85, 42 / 5, 1), _tr(194, 9, 1)''',
  '''T1, T2, T3 = _tr(104, 7, -1), _tr(69, 42 / 5, 1), _tr(158, 9, 1)'''),
 ('''raw_svg("q13", round(_x1 + 26), 262,''', '''raw_svg("q13", round(_x1 + 26), 216,'''),
 # q14: Q 이름표를 대각선 AC 에서 떼어 놓는다
 ('''"Q": {"text": "Q", "position": "NE"}})''', '''"Q": {"text": "Q", "position": "NE", "dx": 7, "dy": 1}})'''),
 # s5b·s6: 깊게 휜 치수가 viewBox 밖으로 나가지 않게 캔버스 확장용 점
 ('''render("s5b", {"A": A, "B": B, "C": C, "D": D, "E": E},''',
  '''render("s5b", {"A": A, "B": B, "C": C, "D": D, "E": E, "Zz": P((B[0] + C[0]) / 2, B[1] + 40)},'''),
 ('''       {"dAD": dim("A", "D", "2"), "dDB": dim("D", "B", "6")},''',
  '''       {"dAD": dim("A", "D", "2"), "dDB": dim("D", "B", "6")},
       labels={"A": "A", "B": "B", "C": "C", "D": "D", "E": "E"},'''),
 ('''render("s6", {"A": A, "B": B, "C": C, "D": Dd, "E": E, "F": F, "G": G, "H": G2},''',
  '''render("s6", {"A": A, "B": B, "C": C, "D": Dd, "E": E, "F": F, "G": G, "H": G2,
              "Zz": P((B[0] + Dd[0]) / 2, B[1] + 50)},'''),
]
for a, b in rep:
    assert s.count(a) == 1, a[:70]
    s = s.replace(a, b)
p.write_text(s, encoding="utf-8")
print("patched")
