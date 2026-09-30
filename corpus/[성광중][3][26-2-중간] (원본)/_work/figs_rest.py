
# ── q2: 좌표평면 사분원 (figure_svg 프리미티브 — 스펙에 사분원 호가 없다) ──
def _arrow(tip, ux, uy, s=4.2):
    px, py = -uy, ux
    a = (tip[0] - ux * s * 1.8 + px * s * 0.75, tip[1] - uy * s * 1.8 + py * s * 0.75)
    b = (tip[0] - ux * s * 1.8 - px * s * 0.75, tip[1] - uy * s * 1.8 - py * s * 0.75)
    return (f'<path d="M {tip[0]:.1f} {tip[1]:.1f} L {a[0]:.1f} {a[1]:.1f} '
            f'L {b[0]:.1f} {b[1]:.1f} Z" fill="#000"/>')


T2 = mk(160, 70, 196)
th2 = math.radians(29)
A2 = T2(math.cos(th2), math.sin(th2))
B2 = T2(math.cos(th2), 0)
D2 = T2(1, 0)
C2 = T2(1, math.tan(th2))
O2 = T2(0, 0)
Y1 = T2(0, 1)
FS2 = type_scale(275, 225)
arc2 = [T2(math.cos(math.radians(a / 2)), math.sin(math.radians(a / 2))) for a in range(0, 181)]
_check("q2-표", abs(math.sin(th2) - 0.4848) < 5e-5 and abs(math.cos(th2) - 0.8746) < 5e-5,
       "sin29°=0.4848, cos29°=0.8746")
_check("q2-BD", abs((1 - math.cos(th2)) - 0.1254) < 1e-4, "BD=1-cos29°=0.1254(정답 ②)")
verify_figure("q2", angles=[(29, O2, D2, A2), (90, B2, A2, O2), (90, D2, C2, O2)],
              on_line=[(A2, O2, C2)], on_circle=[(A2, *O2, 160)])
S["q2"] = f'''<svg viewBox="0 0 275 225" xmlns="http://www.w3.org/2000/svg">
{line(T2(-0.08, 0), T2(1.32, 0), 1.3)}{_arrow(T2(1.32, 0), 1, 0)}
{line(T2(0, -0.08), T2(0, 1.14), 1.3)}{_arrow(T2(0, 1.14), 0, -1)}
{curve_path(arc2, w=1.9)}
{line(O2, C2, 1.9)}
{line(A2, B2, 1.9)}
{line(C2, D2, 1.9)}
{line(T2(0, math.sin(th2)), A2, 1.0, dash="2 3")}
{rangle_at(*B2, A2, O2, 7)}{rangle_at(*D2, C2, O2, 7)}
{txt(O2[0] - 9, O2[1] + 16, "O", FS2, anc="end")}
{txt(Y1[0] - 7, Y1[1] + 5, "1", FS2, anc="end")}
{txt(O2[0] - 7, A2[1] + 5, "0.4848", FS2, anc="end")}
{txt(A2[0] - 6, A2[1] - 9, "A", FS2)}
{txt(C2[0] + 3, C2[1] - 8, "C", FS2, anc="start")}
{txt(B2[0], B2[1] + 17, "B", FS2)}
{txt(D2[0] + 6, D2[1] - 7, "D", FS2, anc="start")}
{txt(D2[0] + 4, D2[1] + 17, "1", FS2, anc="start")}
{txt(T2(1.32, 0)[0] - 2, O2[1] + 17, "x", FS2, it=True)}
{txt(O2[0] + 12, T2(0, 1.14)[1] + 5, "y", FS2, it=True)}
</svg>'''

# ── q6 ────────────────────────────────────────────────────────────────
a6 = 8 * math.sin(math.radians(54)) / math.sin(math.radians(45))
T = mk(21, 30, 200)
A6 = (8 * math.cos(math.radians(81)), 8 * math.sin(math.radians(81)))
sp = {"version": 2,
      "points": pts(T, A=A6, B=(0, 0), C=(a6, 0)),
      "segments": {"AB": ["A", "B"], "BC": ["B", "C"], "CA": ["C", "A"]},
      "angles": {"angA": {"vertex": "A", "points": ["B", "C"], "label": "54°"}},
      "dimensions": {"dimAB": {"points": ["A", "B"], "label": "8", "side": "auto"}},
      "labels": {"A": "A", "B": "B", "C": "C"}}
_check("q6-AC", abs(8 * 0.6 + 8 * 0.8 - 11.2) < 1e-9, "AC=AB·cos54+AB·sin54(∠C=45°)=11.2(정답 ③)")
verify_figure("q6", lengths=[(8, xy(sp, "A"), xy(sp, "B")), (a6, xy(sp, "B"), xy(sp, "C"))],
              angles=[(54, xy(sp, "A"), xy(sp, "B"), xy(sp, "C")),
                      (81, xy(sp, "B"), xy(sp, "A"), xy(sp, "C"))])
S["q6"] = spec_svg(sp)

# ── q7 ────────────────────────────────────────────────────────────────
h7 = 5 * (3 + SQ3)
T = mk(8.4, 22, 215)
sp = {"version": 2,
      "points": pts(T, A=(h7, h7), B=(0, 0), C=(10, 0), H=(h7, 0)),
      "segments": {"AB": ["A", "B"], "AC": ["A", "C"], "AH": ["A", "H"],
                   "BC": ["B", "C"], "CH": ["C", "H"]},
      "angles": {"angB": {"vertex": "B", "points": ["C", "A"], "label": "45°"},
                 "angC": {"vertex": "C", "points": ["H", "A"], "label": "60°"},
                 "angH": {"vertex": "H", "points": ["A", "C"], "right": True}},
      "dimensions": {"dimBC": {"points": ["B", "C"], "label": "10\\ \\mathrm{cm}", "side": "auto"}},
      "labels": {"A": "A", "B": "B", "C": "C", "H": "H"}}
verify_figure("q7", lengths=[(10, xy(sp, "B"), xy(sp, "C")), (h7, xy(sp, "A"), xy(sp, "H"))],
              angles=[(45, xy(sp, "B"), xy(sp, "C"), xy(sp, "A")),
                      (60, xy(sp, "C"), xy(sp, "H"), xy(sp, "A")),
                      (90, xy(sp, "H"), xy(sp, "A"), xy(sp, "C"))])
S["q7"] = spec_svg(sp)

# ── q8 ────────────────────────────────────────────────────────────────
u8 = 30
T = mk(u8, 150, 150)
sp = {"version": 2,
      "points": pts(T, O=(0, 0), A=(-4, 0), B=(4, 0), C=(2, 2 * SQ3)),
      "circles": {"c8": {"center": "O", "radius": 4 * u8, "draw": False}},
      "arcs": {"arcBA": {"circle": "c8", "from": "B", "to": "A", "dir": "ccw"}},
      "segments": {"AB": ["A", "B"], "AC": ["A", "C"], "OC": ["O", "C"]},
      "regions": {"seg8": {"boundary": [
                      {"arc": {"circle": "c8", "from": "C", "to": "A", "dir": "ccw"}},
                      {"seg": ["A", "C"]}], "fill": GRAY},
                  "sec8": {"boundary": [
                      {"seg": ["O", "B"]},
                      {"arc": {"circle": "c8", "from": "B", "to": "C", "dir": "ccw"}},
                      {"seg": ["C", "O"]}], "fill": GRAY}},
      "angles": {"angA": {"vertex": "A", "points": ["B", "C"], "label": "30°"}},
      "dimensions": {"dimAO": {"points": ["A", "O"], "label": "4", "side": "auto"}},
      "labels": {"A": "A", "B": "B", "C": "C", "O": "O"}}
_check("q8-넓이", abs((8 * math.pi - 0.5 * 16 * math.sin(math.radians(120))) - (8 * math.pi - 4 * SQ3)) < 1e-9,
       "반원−△AOC = 8π−4√3(정답 ①)")
verify_figure("q8", lengths=[(4, xy(sp, "A"), xy(sp, "O")), (4, xy(sp, "O"), xy(sp, "C"))],
              angles=[(30, xy(sp, "A"), xy(sp, "B"), xy(sp, "C"))])
S["q8"] = spec_svg(sp, dots=["O"])

# ── q9 ────────────────────────────────────────────────────────────────
T = mk(19, 22, 140)
sp = {"version": 2,
      "points": pts(T, A=(9, 3 * SQ3), B=(0, 0), C=(12, 0), D=(6, 2 * SQ3)),
      "segments": {"AB": ["A", "B"], "BC": ["B", "C"], "CA": ["C", "A"], "CD": ["C", "D"]},
      "regions": {"tri9": {"boundary": [{"seg": ["D", "B"]}, {"seg": ["B", "C"]},
                                        {"seg": ["C", "D"]}], "fill": GRAY}},
      "angles": {"angB": {"vertex": "B", "points": ["C", "D"], "label": "30°"},
                 "angC": {"vertex": "C", "points": ["A", "D"], "label": "30°"}},
      "dimensions": {"dimBC": {"points": ["B", "C"], "label": "12\\ \\mathrm{cm}", "side": "auto"},
                     "dimAC": {"points": ["A", "C"], "label": "6\\ \\mathrm{cm}", "side": "auto"},
                     "dimBA": {"points": ["B", "A"], "label": "6\\sqrt{3}\\ \\mathrm{cm}",
                               "side": "auto"}},
      "labels": {"A": "A", "B": "B", "C": "C", "D": "D"}}
_check("q9-넓이", abs(0.5 * 4 * SQ3 * 6 - 12 * SQ3) < 1e-9, "△BCD=½·BD·AC=12√3(정답 ④)")
verify_figure("q9", lengths=[(12, xy(sp, "B"), xy(sp, "C")), (6, xy(sp, "A"), xy(sp, "C")),
                             (6 * SQ3, xy(sp, "B"), xy(sp, "A"))],
              angles=[(30, xy(sp, "B"), xy(sp, "C"), xy(sp, "A")),
                      (30, xy(sp, "C"), xy(sp, "A"), xy(sp, "D")),
                      (90, xy(sp, "A"), xy(sp, "B"), xy(sp, "C"))],
              on_line=[(xy(sp, "D"), xy(sp, "A"), xy(sp, "B"))])
S["q9"] = spec_svg(sp)

# ── q10 ───────────────────────────────────────────────────────────────
u10 = 14
T = mk(u10, 110, 105)
c10 = math.sqrt(32)
sp = {"version": 2,
      "points": pts(T, O=(0, 0), A=(-6, 0), B=(6, 0), M=(2, 0), C=(2, c10), D=(2, -c10)),
      "circles": {"c10": {"center": "O", "radius": 6 * u10}},
      "segments": {"AB": ["A", "B"], "CD": ["C", "D"]},
      "dimensions": {"dimAM": {"points": ["A", "M"], "label": "8\\ \\mathrm{cm}", "side": "left"},
                     "dimMB": {"points": ["M", "B"], "label": "4\\ \\mathrm{cm}", "side": "left"}},
      "labels": {"A": "A", "B": "B", "C": "C", "D": "D", "O": "O", "M": "M"}}
_check("q10-CD", abs(2 * c10 - 8 * SQ2) < 1e-9, "CD=2√(36-4)=8√2(정답 ④)")
verify_figure("q10", lengths=[(8, xy(sp, "A"), xy(sp, "M")), (4, xy(sp, "M"), xy(sp, "B"))],
              angles=[(90, xy(sp, "M"), xy(sp, "B"), xy(sp, "C"))],
              on_circle=[(xy(sp, "C"), *xy(sp, "O"), 6 * u10), (xy(sp, "D"), *xy(sp, "O"), 6 * u10)])
S["q10"] = spec_svg(sp, dots=["O", "M"])

# ── q11 ───────────────────────────────────────────────────────────────
u11 = 23
T = mk(u11, 110, 108)
sp = {"version": 2,
      "points": pts(T, O=(0, 0), A=(0, 4), B=(-2 * SQ3, -2), C=(2 * SQ3, -2),
                    D=(-SQ3, 1), E=(0, -2), F=(SQ3, 1)),
      "circles": {"out11": {"center": "O", "radius": 4 * u11},
                  "in11": {"center": "O", "radius": 2 * u11}},
      "segments": {"AB": ["A", "B"], "BC": ["B", "C"], "CA": ["C", "A"]},
      "labels": {"A": "A", "B": "B", "C": "C", "D": "D", "E": "E", "F": "F", "O": "O"}}
_check("q11-합", abs((0.5 * (4 * SQ3) ** 2 * SQ3 / 2 + 16 * math.pi) - (12 * SQ3 + 16 * math.pi)) < 1e-9,
       "넓이 합 12√3+16π(정답 ⑤)")
verify_figure("q11", lengths=[(4 * SQ3, xy(sp, "A"), xy(sp, "B")), (4 * SQ3, xy(sp, "B"), xy(sp, "C")),
                              (4 * SQ3, xy(sp, "C"), xy(sp, "A"))],
              tangents=[(xy(sp, "A"), xy(sp, "B"), *xy(sp, "O"), 2 * u11),
                        (xy(sp, "B"), xy(sp, "C"), *xy(sp, "O"), 2 * u11),
                        (xy(sp, "C"), xy(sp, "A"), *xy(sp, "O"), 2 * u11)],
              on_circle=[(xy(sp, "A"), *xy(sp, "O"), 4 * u11)])
S["q11"] = spec_svg(sp, dots=["O"])

# ── q12 ───────────────────────────────────────────────────────────────
u12 = 27
T = mk(u12, 160, 150)
sp = {"version": 2,
      "points": pts(T, O=(0, 0), A=(-5, 0), B=(5, 0), E=(1.8, 2.4), C=(-1.4, 4.8),
                    H=(-1.4, 0), S1=(-3, 0), S2=(3, 0), t3=(1.45, 0.72)),
      "circles": {"big12": {"center": "O", "radius": 5 * u12, "draw": False},
                  "sm12": {"center": "O", "radius": 3 * u12, "draw": False}},
      "arcs": {"arcBA": {"circle": "big12", "from": "B", "to": "A", "dir": "ccw"},
               "arcS": {"circle": "sm12", "from": "S2", "to": "S1", "dir": "ccw"}},
      "segments": {"AB": ["A", "B"], "BC": ["B", "C"], "CH": ["C", "H"], "OE": ["O", "E"]},
      "angles": {"angH": {"vertex": "H", "points": ["C", "B"], "right": True}},
      "dimensions": {"dimOB": {"points": ["O", "B"], "label": "5\\,\\mathrm{cm}", "side": "right"}},
      "labels": {"A": "A", "B": "B", "C": "C", "E": "E", "H": "H", "O": "O",
                 "t3": {"text": "3\\,\\mathrm{cm}", "dx": 0, "dy": 0}}}
_check("q12-CH", abs(24 / 5 - 4.8) < 1e-12, "CH=2·△OBC/OB=24/5(정답 ④)")
verify_figure("q12", lengths=[(5, xy(sp, "O"), xy(sp, "B")), (3, xy(sp, "O"), xy(sp, "E"))],
              angles=[(90, xy(sp, "H"), xy(sp, "C"), xy(sp, "B"))],
              tangents=[(xy(sp, "B"), xy(sp, "C"), *xy(sp, "O"), 3 * u12)],
              on_circle=[(xy(sp, "C"), *xy(sp, "O"), 5 * u12)])
S["q12"] = spec_svg(sp, dots=["O"])

# ── q13: 원 O 에 외접하는 사각형 — 접선길이 a,b,c,d 에서 유도 ─────────
a13 = 4.5
tl = [a13, 13 - a13, 2 + a13, 10 - a13]          # A, B, C, D 에서의 접선 길이
lo, hi = 0.01, 50.0
for _ in range(200):
    mid = (lo + hi) / 2
    if sum(math.atan(mid / t) for t in tl) < math.pi:
        lo = mid
    else:
        hi = mid
r13 = (lo + hi) / 2
phi = [math.atan(r13 / t) for t in tl]            # 반각
ang = 90.0
verts = []
for k in range(4):
    turn = 180.0 - math.degrees(2 * phi[k])
    vdir = ang + turn / 2
    verts.append((r13 / math.sin(phi[k]) * math.cos(math.radians(vdir)),
                  r13 / math.sin(phi[k]) * math.sin(math.radians(vdir))))
    ang += turn
Aq, Bq, Cq, Dq = verts
rot = -math.atan2(Cq[1] - Bq[1], Cq[0] - Bq[0])   # BC 를 수평으로


def _rot(p):
    return (p[0] * math.cos(rot) - p[1] * math.sin(rot), p[0] * math.sin(rot) + p[1] * math.cos(rot))


Aq, Bq, Cq, Dq = map(_rot, (Aq, Bq, Cq, Dq))
u13 = 11
T = mk(u13, 125, 110)
sp = {"version": 2,
      "points": pts(T, O=(0, 0), A=Aq, B=Bq, C=Cq, D=Dq),
      "circles": {"c13": {"center": "O", "radius": r13 * u13}},
      "segments": {"AB": ["A", "B"], "BC": ["B", "C"], "CD": ["C", "D"], "DA": ["D", "A"]},
      "dimensions": {"dimAB": {"points": ["A", "B"], "label": "13\\ \\mathrm{cm}", "side": "auto"},
                     "dimCD": {"points": ["C", "D"], "label": "12\\ \\mathrm{cm}", "side": "auto"}},
      "labels": {"A": "A", "B": "B", "C": "C", "D": "D", "O": "O"}}
_check("q13-피토", abs(math.dist(Aq, Bq) + math.dist(Cq, Dq) - math.dist(Aq, Dq) - math.dist(Bq, Cq)) < 1e-6,
       "AB+CD=AD+BC")
_check("q13-AD", abs(math.dist(Aq, Dq) - 10) < 1e-6 and abs(math.dist(Bq, Cq) - 15) < 1e-6,
       "AD=10, BC=15 (2:3, 정답 ①)")
P13 = {k: xy(sp, k) for k in "OABCD"}
verify_figure("q13", lengths=[(13, P13["A"], P13["B"]), (12, P13["C"], P13["D"]),
                              (10, P13["A"], P13["D"]), (15, P13["B"], P13["C"])],
              tangents=[(P13[p], P13[q], *P13["O"], r13 * u13) for p, q in ("AB", "BC", "CD", "DA")])
S["q13"] = spec_svg(sp, dots=["O"])

# ── q14 ───────────────────────────────────────────────────────────────
u14 = 19
T = mk(u14, 30, 185)
E14 = (6, 0)
dAE = (E14[0] - 0, E14[1] - 8)
tH = ((8 - 0) * dAE[0] + (4 - 8) * dAE[1]) / (dAE[0] ** 2 + dAE[1] ** 2)
H14 = (0 + tH * dAE[0], 8 + tH * dAE[1])
sp = {"version": 2,
      "points": pts(T, A=(0, 8), B=(0, 0), C=(12, 0), D=(12, 8), O=(8, 4), E=E14,
                    F=(12, 4), G=(8, 8), H=H14, I=(8, 0)),
      "circles": {"c14": {"center": "O", "radius": 4 * u14}},
      "segments": {"AB": ["A", "B"], "BC": ["B", "C"], "CD": ["C", "D"], "DA": ["D", "A"],
                   "AE": ["A", "E"]},
      "dimensions": {"dimAD": {"points": ["A", "D"], "label": "12\\,\\mathrm{cm}", "side": "auto"},
                     "dimAB": {"points": ["A", "B"], "label": "8\\,\\mathrm{cm}", "side": "auto"}},
      "labels": {k: k for k in "ABCDEFGHIO"}}
_check("q14-EI", abs((8 - 6) - 2) < 1e-12 and abs(math.hypot(6, 8) - (8 + 2)) < 1e-12,
       "AE=AH+HE=8+2=10, EI=2(정답 ③)")
P14 = {k: xy(sp, k) for k in "ABCDEFGHIO"}
verify_figure("q14", lengths=[(12, P14["A"], P14["D"]), (8, P14["A"], P14["B"])],
              tangents=[(P14["A"], P14["E"], *P14["O"], 4 * u14),
                        (P14["B"], P14["C"], *P14["O"], 4 * u14),
                        (P14["C"], P14["D"], *P14["O"], 4 * u14),
                        (P14["D"], P14["A"], *P14["O"], 4 * u14)],
              on_circle=[(P14["H"], *P14["O"], 4 * u14)])
S["q14"] = spec_svg(sp, dots=["O"])

# ── q15: 외접하는 두 원(r, 2r)과 두 접선 ─────────────────────────────
r15 = math.sqrt(32)
al = math.asin(1 / 3)
dl = (math.cos(math.pi / 2 + al), math.sin(math.pi / 2 + al))
dr = (math.cos(math.pi / 2 - al), math.sin(math.pi / 2 - al))
u15 = 4.2
T = mk(u15, 120, 232)
sp = {"version": 2,
      "points": pts(T, P=(0, 0), O=(0, 3 * r15), Op=(0, 6 * r15),
                    A=(16 * dl[0], 16 * dl[1]), B=(32 * dl[0], 32 * dl[1]),
                    C=(16 * dr[0], 16 * dr[1]), D=(32 * dr[0], 32 * dr[1]),
                    L=(46 * dl[0], 46 * dl[1]), R=(46 * dr[0], 46 * dr[1])),
      "circles": {"sm15": {"center": "O", "radius": r15 * u15},
                  "bg15": {"center": "Op", "radius": 2 * r15 * u15}},
      "segments": {"PL": ["P", "L"], "PR": ["P", "R"]},
      "regions": {"sh15": {"boundary": [
          {"arc": {"circle": "sm15", "from": "A", "to": "C", "dir": "ccw"}},
          {"arc": {"circle": "sm15", "from": "C", "to": "A", "dir": "ccw"}}], "fill": GRAY}},
      "dimensions": {"dimAB": {"points": ["A", "B"], "label": "16\\,\\mathrm{cm}", "side": "auto"},
                     "dimPC": {"points": ["P", "C"], "label": "16\\,\\mathrm{cm}", "side": "auto"}},
      "labels": {"A": "A", "B": "B", "C": "C", "D": "D", "P": "P", "O": "O", "Op": "O'"}}
_check("q15-넓이", abs(math.pi * r15 ** 2 - 32 * math.pi) < 1e-9, "작은 원 넓이 32π(정답 ②)")
P15 = {k: xy(sp, k) for k in ("P", "O", "Op", "A", "B", "C", "D", "L", "R")}
verify_figure("q15", lengths=[(16, P15["A"], P15["B"]), (16, P15["P"], P15["C"]),
                              (3 * r15, P15["O"], P15["Op"])],
              tangents=[(P15["P"], P15["L"], *P15["O"], r15 * u15),
                        (P15["P"], P15["L"], *P15["Op"], 2 * r15 * u15),
                        (P15["P"], P15["R"], *P15["O"], r15 * u15),
                        (P15["P"], P15["R"], *P15["Op"], 2 * r15 * u15)],
              on_circle=[(P15["A"], *P15["O"], r15 * u15), (P15["B"], *P15["Op"], 2 * r15 * u15)])
S["q15"] = spec_svg(sp, dots=["O", "Op"])

# ── q16 ───────────────────────────────────────────────────────────────
u16 = 5.2
T = mk(u16, 175, 118)
sp = {"version": 2,
      "points": pts(T, O=(0, 0), A=(-30, 0), D=(-18, 0), P=(-10.8, 14.4), Q=(-10.8, -14.4),
                    B=(-18, 9), C=(-18, -9)),
      "circles": {"c16": {"center": "O", "radius": 18 * u16}},
      "segments": {"AP": ["A", "P"], "AQ": ["A", "Q"], "AO": ["A", "O"], "BC": ["B", "C"],
                   "OQ": ["O", "Q"]},
      "angles": {"angQ": {"vertex": "Q", "points": ["O", "A"], "right": True}},
      "dimensions": {"dimAC": {"points": ["A", "C"], "label": "15\\,\\mathrm{cm}", "side": "auto"},
                     "dimCQ": {"points": ["C", "Q"], "label": "9\\,\\mathrm{cm}", "side": "auto"}},
      "labels": {"A": "A", "B": "B", "C": "C", "D": "D", "O": "O", "P": "P", "Q": "Q"}}
_check("q16-r", abs((12 + 18) ** 2 - (24 ** 2 + 18 ** 2)) < 1e-9, "(12+r)²=24²+r² → r=18(정답 ⑤)")
P16 = {k: xy(sp, k) for k in "OADPQBC"}
verify_figure("q16", lengths=[(15, P16["A"], P16["C"]), (9, P16["C"], P16["Q"])],
              tangents=[(P16["A"], P16["P"], *P16["O"], 18 * u16),
                        (P16["A"], P16["Q"], *P16["O"], 18 * u16),
                        (P16["B"], P16["C"], *P16["O"], 18 * u16)],
              angles=[(90, P16["Q"], P16["O"], P16["A"])])
S["q16"] = spec_svg(sp, dots=["O"])

# ── q17: 정사각형 속 원 5개 (figure_svg 프리미티브) ───────────────────
s17 = 4 + 4 * SQ2
u17 = 20
o17 = 14
T17 = lambda x, y: (o17 + u17 * x, o17 + u17 * (s17 - y))  # noqa: E731
ctr = [(2, 2), (s17 - 2, 2), (2, s17 - 2), (s17 - 2, s17 - 2), (s17 / 2, s17 / 2)]
side = u17 * s17
vb17 = int(side + 2 * o17)
_check("q17-변", all(abs(math.dist(c, ctr[4]) - 4) < 1e-9 for c in ctr[:4]),
       "귀퉁이 원과 가운데 원이 접함(중심거리 4) → 한 변 4+4√2(정답 ②)")
verify_figure("q17", lengths=[(4, T17(*ctr[0]), T17(*ctr[4])), (4, T17(*ctr[3]), T17(*ctr[4])),
                              (s17, T17(0, 0), T17(s17, 0))],
              tangents=[(T17(0, 0), T17(s17, 0), *T17(*ctr[0]), 2 * u17),
                        (T17(0, 0), T17(0, s17), *T17(*ctr[0]), 2 * u17),
                        (T17(s17, s17), T17(s17, 0), *T17(*ctr[3]), 2 * u17)])
circles17 = "\n".join(
    f'<circle cx="{T17(*c)[0]:.2f}" cy="{T17(*c)[1]:.2f}" r="{2 * u17}" fill="{GRAY}" '
    f'stroke="#000" stroke-width="1.6"/>' for c in ctr)
S["q17"] = f'''<svg viewBox="0 0 {vb17} {vb17}" xmlns="http://www.w3.org/2000/svg">
{circles17}
<rect x="{o17}" y="{o17}" width="{side:.2f}" height="{side:.2f}" fill="none" stroke="#000" stroke-width="1.9"/>
</svg>'''

# ── q18: 원을 AB 로 접어 P 가 O 에 겹침 ────────────────────────────────
R18 = 4 * SQ3
u18 = 13.5
T = mk(u18, 125, 110)
sp = {"version": 2,
      "points": pts(T, O=(0, 0), A=(-6, -2 * SQ3), B=(6, -2 * SQ3), M=(0, -2 * SQ3),
                    P=(0, -R18), Q=(0, -3 * SQ3)),
      "circles": {"c18": {"center": "O", "radius": R18 * u18, "draw": False},
                  "f18": {"center": "P", "radius": R18 * u18, "draw": False}},
      "arcs": {"up18": {"circle": "c18", "from": "B", "to": "A", "dir": "ccw"},
               "lo18": {"circle": "c18", "from": "A", "to": "B", "dir": "ccw", "dash": "4 3"},
               "fold18": {"circle": "f18", "from": "B", "to": "A", "dir": "ccw"}},
      "segments": {"AB": ["A", "B"], "OM": ["O", "M"], "MQ": ["M", "Q"], "QP": ["Q", "P"],
                   "AP": ["A", "P"], "AQ": ["A", "Q"]},
      "regions": {"cap18": {"boundary": [
                      {"arc": {"circle": "f18", "from": "B", "to": "A", "dir": "ccw"}},
                      {"seg": ["A", "B"]}], "fill": "#efefef"},
                  "tri18": {"boundary": [{"seg": ["A", "P"]}, {"seg": ["P", "Q"]},
                                         {"seg": ["Q", "A"]}], "fill": "#c8c8c8"}},
      "labels": {"A": "A", "B": "B", "O": "O", "M": "M", "P": "P", "Q": "Q"}}
_check("q18-넓이", abs(0.5 * SQ3 * 6 - 3 * SQ3) < 1e-12, "△APQ=½·PQ·AM=3√3(정답 ①)")
P18 = {k: xy(sp, k) for k in "OABMPQ"}
verify_figure("q18", lengths=[(2 * SQ3, P18["O"], P18["M"]), (2 * SQ3, P18["M"], P18["P"]),
                              (SQ3, P18["M"], P18["Q"]), (SQ3, P18["Q"], P18["P"]),
                              (6, P18["A"], P18["M"])],
              on_circle=[(P18["A"], *P18["O"], R18 * u18), (P18["O"], *P18["P"], R18 * u18),
                         (P18["P"], *P18["O"], R18 * u18)],
              angles=[(90, P18["M"], P18["B"], P18["O"])])
S["q18"] = spec_svg(sp, dots=["O"])

# 원본 문항 순서로 정렬
S = {k: S[k] for k in sorted(S, key=lambda k: int(k[1:]))}

