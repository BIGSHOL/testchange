p="fig_svgs.py"; s=open(p,encoding="utf-8").read()
def R(a,b):
    global s
    assert a in s, a[:60]
    s=s.replace(a,b)
R('''        labels=None, circles=None, extra=""):
    spec = {"version": 2,''','''        labels=None, circles=None, extra="", arcs=None, canvas_fixed=False):
    spec = {"version": 2,''')
R('''    if circles:
        spec["circles"] = circles''','''    if canvas_fixed:
        spec["canvas"] = list(canvas)
    if circles:
        spec["circles"] = circles
    if arcs:
        spec["arcs"] = arcs''')
R('''    S[key] = sanitize_svg(render_graph(spec))
    pad = 48''','''    S[key] = sanitize_svg(graph_math(render_graph(spec)))
    pad = 48''')
R('''def region(*names):''','''def graph_math(svg):
    """graph-1 라벨은 평문 <text> 로 나온다(웹은 data-mj 로 따로 조판) — 변수만 이탤릭으로."""
    svg = re.sub(r'(<text [^>]*data-mj="([a-z])"[^>]*)>', r'\1 font-style="italic">', svg)
    return svg.replace(">$y=-3$</text>", '><tspan font-style="italic">y</tspan> = −3</text>')


def unit_upright(svg):
    """라벨 조판기가 단위 m 를 변수로 보고 기울인다 — 정자로 되돌린다."""
    return re.sub(r'<tspan font-style="italic"( font-family="[^"]*")?>m</tspan>',
                  r'<tspan font-style="normal">m</tspan>', svg)


def region(*names):''')
R("import math\nimport os\n","import math\nimport os\nimport re\n")
# q9
R('''geo("q9", (245, 235), pts9, seg_map("OE", "OB", "BD", "OA", "AC", "AB", "CD"),
    circles={"q": {"center": "O", "radius": 150, "draw": False}},''','''spec9 = dict(pts9)
spec9["E"] = {"type": "on_circle", "circle": "q", "angle": 90}
spec9["D"] = {"type": "on_circle", "circle": "q", "angle": 0}
spec9["A"] = {"type": "on_circle", "circle": "q", "angle": 42}
geo("q9", (245, 235), spec9, seg_map("OE", "OB", "BD", "OA", "AC", "AB", "CD"),
    circles={"q": {"center": "O", "radius": 150, "draw": False}},
    arcs={"arcED": {"circle": "q", "from": "E", "to": "D", "dir": "cw"}},''')
R('''    dims={"dimOE": {"points": ["O", "E"], "label": "1"}},
    extra=(f'<path d="M {pts9["E"][0]} {pts9["E"][1]} A 150 150 0 0 1 '
           f'{pts9["D"][0]} {pts9["D"][1]}" fill="none" stroke="#111111" stroke-width="1.9"/>'))''','''    dims={"dimOE": {"points": ["O", "E"], "label": "1"}})''')
R('''geo("q10", (215, 240), pts10, seg_map("OT", "OD", "DA", "OB", "BC", "BD", "AC"),''','''spec10 = dict(pts10)
spec10["T"] = {"type": "on_circle", "circle": "q", "angle": 90}
spec10["A"] = {"type": "on_circle", "circle": "q", "angle": 0}
spec10["B"] = {"type": "on_circle", "circle": "q", "angle": math.degrees(X10)}
geo("q10", (215, 240), spec10, seg_map("OT", "OD", "DA", "OB", "BC", "BD", "AC"),
    circles={"q": {"center": "O", "radius": 112, "draw": False}},
    arcs={"arcTA": {"circle": "q", "from": "T", "to": "A", "dir": "cw"}},''')
R('''    labels={k: k for k in "OABCD"},
    extra=(f'<path d="M {pts10["T"][0]} {pts10["T"][1]} A 112 112 0 0 1 '
           f'{pts10["A"][0]} {pts10["A"][1]}" fill="none" stroke="#111111" stroke-width="1.9"/>'))''','''    labels={k: k for k in "OABCD"})''')
# units
R('"label": "200 m"}})','"label": "200 m"}})\nS["q12"] = unit_upright(S["q12"])')
R('"label": "20 m"}})', '"label": "20 m"}}, canvas_fixed=True)')
R('S["q17"] = S["q17"].replace(', 'S["q17"] = unit_upright(S["q17"]).replace(')
# q14 shear
R("return (round(122 + 50 * (x - 0.45 * y), 3)","return (round(128 + 50 * (x - 0.65 * y), 3)")
# s1 label 1
R('{"at": [1, 0], "text": "1", "dx": 8, "dy": 18}','{"at": [1, 0], "text": "1", "dx": -9, "dy": 18}')
open(p,"w",encoding="utf-8").write(s)
