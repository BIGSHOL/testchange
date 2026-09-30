# -*- coding: utf-8 -*-
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "fig_svgs.py"
s = p.read_text(encoding="utf-8")


def R(a, b):
    global s
    assert a in s, a[:80]
    s = s.replace(a, b)


R('"domain": [-2.32, 0.34]', '"domain": [-2.34, 0.34]')

# q7 — AC 는 라벨이 없으므로 원본 비율(AC:BC ≈ 0.64)을 따른다.
R('pts7 = {"B": P7((0, 0)), "C": P7((4, 0)), "A": P7((4, 2 * math.sqrt(5)))}',
  '# 원본 시각 비율: AC 는 라벨이 없어 원본(AC/BC≈0.64)을 따른다(정답 계산값 2√5 는 그림에 없음).\n'
  'pts7 = {"B": P7((0, 0)), "C": P7((4, 0)), "A": P7((4, 0.64 * 4))}')
R('''verify_figure("q7", lengths=[(4, pts7["B"], pts7["C"]), (2 * math.sqrt(5), pts7["C"], pts7["A"]),
                             (6, pts7["A"], pts7["B"])],''',
  '''verify_figure("q7", lengths=[(4, pts7["B"], pts7["C"])],''')

# q13 — 라벨은 AB=5·AC=8 뿐. ∠A 는 원본 시각(≈62°)을 따른다.
R('''pts13 = {"B": P13((0, 0)), "C": P13((BC13, 0)), "A": P13((xa, math.sqrt(25 - xa * xa)))}''',
  '''ANG13 = 62.0                                  # 원본 그림의 ∠A 시각값(라벨 없음)
BC13 = math.sqrt(25 + 64 - 80 * math.cos(math.radians(ANG13)))
xa = (BC13 ** 2 - 39) / (2 * BC13)
P13 = mapper(40, 150, 22)
pts13 = {"B": P13((0, 0)), "C": P13((BC13, 0)), "A": P13((xa, math.sqrt(25 - xa * xa)))}''')
R('''              angles=[(math.degrees(math.acos(cosA)), pts13["A"], pts13["B"], pts13["C"])])''',
  '''              angles=[(ANG13, pts13["A"], pts13["B"], pts13["C"])])''')

# q14 — HD 가 원본처럼 오른쪽 위로 기울게(x 항 추가). 화면상 직각이 아니라 직각표시는 직접 그림.
R("return (round(128 + 50 * (x - 0.65 * y), 3), round(152 - 50 * (z + 0.35 * y), 3))",
  "return (round(128 + 50 * (x - 0.65 * y), 3), round(152 - 50 * (z + 0.35 * y + 0.22 * x), 3))")
R('''    angles={"angH": {"vertex": "H", "points": ["A", "D"], "right": True},''',
  '''    canvas_fixed=True, extra=HMARK14,
    angles={''')
open_idx = s.index("pts14 = {k: proj14(v)")
line_end = s.index("\n", open_idx)
s = s[:line_end + 1] + (
    "_hx, _hy = pts14[\"H\"]\n"
    "_u = (pts14[\"A\"][0] - _hx, pts14[\"A\"][1] - _hy)\n"
    "_v = (pts14[\"D\"][0] - _hx, pts14[\"D\"][1] - _hy)\n"
    "_lu, _lv = math.hypot(*_u), math.hypot(*_v)\n"
    "HMARK14 = rangle(_hx, _hy, _u[0] / _lu, _u[1] / _lu, _v[0] / _lv, _v[1] / _lv, 8)\n"
) + s[line_end + 1:]
R("from core.figure_svg import lint_svg, sqrt_label, unverified, verify_figure",
  "from core.figure_svg import lint_svg, rangle, sqrt_label, unverified, verify_figure")
R("""verify_figure("q14", on_line=[(pts14["H"], pts14["M"], pts14["D"]), (pts14["M"], pts14["B"], pts14["C"])],
              angles=[(90, pts14["H"], pts14["A"], pts14["D"])])""", """verify_figure("q14", on_line=[(pts14["H"], pts14["M"], pts14["D"]), (pts14["M"], pts14["B"], pts14["C"])])""")
p.write_text(s, encoding="utf-8")
print("edited")
