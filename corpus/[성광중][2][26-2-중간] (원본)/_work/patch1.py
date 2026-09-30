import os
p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fig_svgs.py")
s = open(p, encoding="utf-8").read()
R = [
('''_LBL_RE = re.compile(''', '''def alabel(v, p1, p2, content, d=26, fs=15):
    """각 라벨을 손으로 — 엔진 자동배치가 각 밖으로 밀어낸 경우만(halo_angle 은
    두 변을 침범하지 않을 만큼 이등분선을 따라 스스로 민다)."""
    from core.figure_svg import halo_angle
    return halo_angle(v[0], v[1], p1, p2, d, content, fs)


_IT = '<tspan font-style="italic">{}</tspan>'


_LBL_RE = re.compile('''),
('''    "angles": {"angF": {"vertex": "F", "points": ["A", "E"], "label": "63°", "label_distance": 30},
               "angE": {"vertex": "E", "points": ["C", "D"], "label": "41°", "label_distance": 32}},
    "labels": {"A": "A", "B": "B", "C": "C", "D": "D", "E": "E", "F": "F"},
})''', '''    "angles": {"angF": {"vertex": "F", "points": ["A", "E"]},
               "angE": {"vertex": "E", "points": ["C", "D"]}},
    "labels": {"A": "A", "B": "B", "C": "C", "D": "D", "E": "E", "F": "F"},
}, extras=lambda T: alabel(T(F5), T(A5), T(E5), "63°", 30)
   + alabel(T(E5), T(C5), T(D5), "41°", 32))'''),
('''    "angles": {"angI": {"vertex": "I", "points": ["B", "C"], "label": "110°", "label_distance": 26},''',
 '''    "angles": {"angI": {"vertex": "I", "points": ["B", "C"]},'''),
('''    "labels": {"A": "A", "B": "B", "C": "C", "I": "I", "O": "O"},
})''', '''    "labels": {"A": "A", "B": "B", "C": "C", "I": "I", "O": "O"},
}, extras=lambda T: alabel(T(I8), T(B8), T(C8), "110°", 27))'''),
('''    "angles": {"angC": {"vertex": "C", "points": ["B", "A"], "label": "120°", "label_distance": 36},
               "angD": {"vertex": "D", "points": ["A", "B"], "label": "z°", "label_distance": 34}},''',
 '''    "angles": {"angC": {"vertex": "C", "points": ["B", "D"]}},'''),
('''    return "\\n".join([wedge(T(D9), T(A9), T(C9), 16), bo,''', '''    return "\\n".join([wedge(T(D9), T(A9), T(C9), 16), bo,
                      alabel(T(C9), T(B9), T(A9), "120°", 30),
                      alabel(T(D9), T(A9), T(B9), _IT.format("z") + "°", 30),'''),
('''               "angy": {"vertex": "E", "points": ["A", "D"], "label": "y", "label_distance": 20},''',
 '''               "angy": {"vertex": "E", "points": ["A", "D"]},'''),
('''    "labels": {"A": "A", "B": "B", "C": "C", "D": "D", "O": "O", "E": "E", "F": "F"},
})

# ══ q15''', '''    "labels": {"A": "A", "B": "B", "C": "C", "D": "D", "O": "O", "E": "E", "F": "F"},
}, extras=lambda T: alabel(T(E14), T(A14), T(D14), _IT.format("y"), 20))

# ══ q15'''),
('fill="#e2e2e2" stroke="none"/>', 'fill="#ededed" stroke="none"/>'),
('fill="#bdbdbd" stroke="none"/>', 'fill="#c4c4c4" stroke="none"/>'),
('fill="#a9a9a9" stroke="none"/>\',', 'fill="#ebebeb" stroke="none"/>\','),
('fill="#c8c8c8" stroke="none"/>\',', 'fill="#f4f4f4" stroke="none"/>\','),
('fill="#dcdcdc" stroke="none"/>\',', 'fill="#efefef" stroke="none"/>\','),
('_L2, _t2 = _lighthouse(215.0, _b18, 12)', '_L2, _t2 = _lighthouse(240.0, _b18, 12)'),
('{_hdim(150.0, _t2, _b18, "12 m")}', '{_hdim(165.0, _t2, _b18, "12 m")}'),
('(12, (150, _t2), (150, _b18))', '(12, (165, _t2), (165, _b18))'),
('<svg viewBox="0 0 320 195" xmlns="http://www.w3.org/2000/svg">\n<rect width="320" height="195"',
 '<svg viewBox="0 0 350 195" xmlns="http://www.w3.org/2000/svg">\n<rect width="350" height="195"'),
("\n\n_IT = '<tspan font-style=\"italic\">{}</tspan>'\nV = {", "\n\nV = {"),
]
for a, b in R:
    assert a in s, a
    s = s.replace(a, b)
open(p, "w", encoding="utf-8").write(s)
print("patched")
