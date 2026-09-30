from pathlib import Path
p = Path(__file__).resolve().parents[1] / "fig_svgs.py"
s = p.read_text(encoding="utf-8")


def rep(old, new, cnt=1):
    global s
    assert s.count(old) == cnt, (old, s.count(old))
    s = s.replace(old, new)


# build(): pos= 로 라벨 방향 지정
rep('''def build(key, F, segs, angles=None, dims=None, labels=None, extra=None, dots=(),
          points=None):''', '''def build(key, F, segs, angles=None, dims=None, labels=None, extra=None, dots=(),
          points=None, pos=None):''')
rep('''    spec["labels"] = labels if labels is not None else {n: n for n in names if len(n) == 1}''',
    '''    spec["labels"] = labels if labels is not None else {n: n for n in names if len(n) == 1}
    for n, where in (pos or {}).items():
        spec["labels"][n] = {"text": n, "position": where}''')

# 엔진 글꼴로 덧쓰는 텍스트
rep('''def seg_spec(item):''', '''ENGINE_FONT = "Cambria Math, HancomEQN, Times New Roman, serif"


def etxt(x, y, s, fs=16.8, anc="middle"):
    return (f'<text x="{x:.2f}" y="{y:.2f}" font-family="{ENGINE_FONT}" font-size="{fs}" '
            f'text-anchor="{anc}" fill="#111111">{s}</text>')


def seg_spec(item):''')
rep('from core.figure_svg import (bisect_pt, dot, isect, lint_svg,  # noqa: E402\n                             unverified, verify_figure)',
    'from core.figure_svg import (bisect_pt, dot, isect, leader, lint_svg, meas,  # noqa: E402\n                             unverified, verify_figure)')

# q1: 같음 표시 2개, 외각 호 크게
rep('build("q1", F, [("AB", {"ticks": 1}), ("AC", {"ticks": 1}), "BC", "BX"],',
    'build("q1", F, [("AB", {"ticks": 2}), ("AC", {"ticks": 2}), "BC", "BX"],')
rep('"label": "x", "radius": 15}},\n      labels={"A": "A", "B": "B", "C": "C"})',
    '"label": "x", "radius": 20}},\n      labels={"A": "A", "B": "B", "C": "C"})')
# q4: A·D 이름은 꼭짓점 위
rep('''              "angF": {"vertex": "F", "points": ["D", "E"], "right": True}})''',
    '''              "angF": {"vertex": "F", "points": ["D", "E"], "right": True}},
      pos={"A": "N", "D": "N"})''')
# q6: x 는 꼭짓점 A 가까이, O 이름은 아래
rep('"angA": {"vertex": "A", "points": ["B", "O"], "label": "x"}},\n      dots=("O",))',
    '"angA": {"vertex": "A", "points": ["B", "O"], "label": "x",\n                       "label_distance": 30}},\n      dots=("O",), pos={"O": "S"})')
# q8: I 는 왼쪽 아래
rep('''      dots=("I",),
      extra=lambda T: [cross_in''', '''      dots=("I",), pos={"I": "SW"},
      extra=lambda T: [cross_in''')
# q10: 30° 는 지시선으로(원본 인쇄 방식)
rep('''      angles={"angIBO": {"vertex": "B", "points": ["I", "O"], "label": "30°",
                         "radius": 30}},
      dots=("I", "O"),
      extra=lambda T: [dot_in(T("B"), T("A"), T("I"), 44, 2.1),
                       dot_in(T("B"), T("I"), T("C"), 52, 2.1)])''',
    '''      angles={"angIBO": {"vertex": "B", "points": ["I", "O"], "radius": 30}},
      dots=("I", "O"),
      extra=lambda T: [dot_in(T("B"), T("A"), T("I"), 44, 2.1),
                       dot_in(T("B"), T("I"), T("C"), 52, 2.1),
                       leader((T("B")[0] + 22, T("B")[1] + 50),
                              bisect_pt(*T("B"), T("I"), T("O"), 30.5), gap=8.0, w=0.72),
                       etxt(T("B")[0] + 22, T("B")[1] + 64, "30°")])''')
# q15: O 는 왼쪽 아래
rep('''              "angD": {"vertex": "D", "points": ["A", "O"], "label": "y"}})''',
    '''              "angD": {"vertex": "D", "points": ["A", "O"], "label": "y"}},
      pos={"O": "SW"})''')
# q16: F 아래, O 왼쪽 위, E 위
rep('''            "dimBC": {"points": ["B", "C"], "label": "14 cm", "side": "auto"}})''',
    '''            "dimBC": {"points": ["B", "C"], "label": "14 cm", "side": "auto"}},
      pos={"F": "S", "O": "NW", "E": "N"})''')
# s4: O 아래
rep('''      dims={"dimAO": {"points": ["A", "O"], "label": "2 cm", "side": "auto"}})''',
    '''      dims={"dimAO": {"points": ["A", "O"], "label": "2 cm", "side": "auto"}},
      pos={"O": "S"})''')
# s3: (4) 확대, 번호 더 왼쪽, OD·OB 치수는 지시선(원본 방식)
rep('F4 = Frame(p4, 21, 355, 225)', 'F4 = Frame(p4, 24, 360, 225)')
for i in "1234":
    rep(f'self.m["n{i}"] = (F{i}.ox - 28, F{i}.oy + 2)', f'self.m["n{i}"] = (F{i}.ox - 40, F{i}.oy + 2)')
rep('''            "dimOD4": {"points": ["O4", "D4"], "label": "2 cm"},
            "dimOB4": {"points": ["O4", "B4"], "label": "4 cm"}},
      labels=lab3)''', '''            },
      labels=lab3, extra=s3_extra)''')
rep('''            "dimAO4": {"points": ["A4", "O4"], "label": "3 cm"},
            "dimOC4": {"points": ["O4", "C4"], "label": "3 cm"},''',
    '''            "dimAO4": {"points": ["A4", "O4"], "label": "3 cm", "side": "left"},
            "dimOC4": {"points": ["O4", "C4"], "label": "3 cm", "side": "left"},''')
rep('''build("s3", M, segs3,''', '''def s3_extra(T):
    """OD=2 cm·OB=4 cm — 원본처럼 치수 점선 + 바깥 라벨에서 지시선 화살표."""
    O, D, B = T("O4"), T("D4"), T("B4")
    mOD = ((O[0] + D[0]) / 2, (O[1] + D[1]) / 2)
    mOB = ((O[0] + B[0]) / 2, (O[1] + B[1]) / 2)
    return [meas(*O, *D, 9), meas(*O, *B, 9),
            leader((D[0] + 24, mOD[1] + 4), (mOD[0] + 9, mOD[1] + 6), gap=4.0, w=0.72),
            etxt(D[0] + 40, mOD[1] + 2, "2 cm"),
            leader((B[0] - 30, mOB[1] - 2), (mOB[0] - 9, mOB[1] - 6), gap=4.0, w=0.72),
            etxt(B[0] - 44, mOB[1] + 10, "4 cm")]


build("s3", M, segs3,''')
p.write_text(s, encoding="utf-8")
print("patched")
