# -*- coding: utf-8 -*-
"""1차 검수 반영 — q2 치수 방향·여백, q4 크기·H 라벨, q11 B 라벨, 덧그림 이탤릭 글꼴, lint 예외."""
from pathlib import Path
p = Path(__file__).resolve().parents[1] / "fig_svgs.py"
s = p.read_text(encoding="utf-8")
rep = [
 # 덧그림 라벨도 스펙과 같은 이탤릭 글꼴(수식 글꼴엔 이탤릭 판이 없다)
 ('''            f'text-anchor="{anc}" fill="#111111">{label_pieces_svg(label, fs)}</text>')''',
  '''            f'text-anchor="{anc}" fill="#111111">{label_pieces_svg(label, fs, ITALIC_FONT)}</text>')'''),
 ('''GRAY = "#e3e3e3"''', '''ITALIC_FONT = "Cambria, Times New Roman, serif"   # StyleProfile.font_family_italic 과 동일
GRAY = "#e3e3e3"'''),
 # q2 ㄱ: 왼쪽으로 옮기고 바깥 호를 키워 D·E 이름표가 호 안쪽에 들어가게
 ("_f = frame(62, 196, 11.5)\n_a = sss(16, 12, 13.7)", "_f = frame(50, 196, 11.5)\n_a = sss(16, 12, 13.7)"),
 ('''    out += [meas(*A, *D, 8), adim(A, B, 24, "16 cm", t=0.60),
            meas(*A, *E, -8), adim(A, C, -24, "12 cm", t=0.62)]''',
  '''    out += [meas(*A, *D, 8), adim(A, B, 32, "16 cm", t=0.58),
            meas(*A, *E, -8), adim(A, C, -30, "12 cm", t=0.60)]'''),
 ('''    lx, ly = A[0] - 92, A[1] + 12''', '''    lx, ly = A[0] - 104, A[1] + 4'''),
 ('''    lx, ly = A[0] + 56, A[1] + 14''', '''    lx, ly = A[0] + 58, A[1] + 6'''),
 # q2 ㄴ·ㄷ·ㅂ: 치수 호를 도형 바깥쪽으로
 ('''    out += [adim(D, E, -9, "2 cm"), adim(E, A, 9, "3 cm"), adim(A, C, 9, "6 cm"), adim(C, B, 9, "4 cm")]''',
  '''    out += [adim(D, E, 9, "2 cm"), adim(E, A, 9, "3 cm"), adim(A, C, -9, "6 cm"), adim(C, B, -9, "4 cm")]'''),
 ('''    out += [adim(E, D, 9, "4 cm"), adim(E, A, -9, "3 cm"), adim(A, C, 9, "5 cm"), adim(B, C, -9, "6 cm")]''',
  '''    out += [adim(E, D, -9, "4 cm"), adim(E, A, 9, "3 cm"), adim(A, C, -9, "5 cm"), adim(B, C, 9, "6 cm")]'''),
 ('''    out += [adim(B, D, 14, "20 cm", t=0.22), adim(A, D, -9, "8 cm"),''',
  '''    out += [adim(B, D, -14, "20 cm", t=0.20), adim(A, D, 9, "8 cm"),'''),
 # q4: 원본 크기에 가깝게 키움
 ('''C = P(160, 208)
A, B = polar(C, 120, 120), polar(C, 160, 120)
Ff = P(338, 192)
Dd, Ee = polar(Ff, 140, 100), polar(Ff, 180, 100)
Ii = P(452, 142)
Gg, Hh = polar(Ii, 194, 60), polar(Ii, 234, 60)''',
  '''C = P(178, 222)
A, B = polar(C, 120, 140), polar(C, 160, 140)
Ff = P(372, 204)
Dd, Ee = polar(Ff, 140, 118), polar(Ff, 180, 118)
Ii = P(502, 150)
Gg, Hh = polar(Ii, 194, 70), polar(Ii, 234, 70)'''),
 ('''              "Z1": P(20, 52), "Z2": P(490, 222)},''', '''              "Z1": P(14, 54), "Z2": P(532, 238)},'''),
 ('''       labels={k: k for k in "ABCDEFGHI"},
       pre=_q4_poles,''', '''       labels={**{k: k for k in "ABCDEFGI"}, "H": {"text": "H", "position": "SW"}},
       pre=_q4_poles,'''),
 ('''       post=lambda sh: "".join(txt(*sh((x, 70)), name, 15)
                               for x, name in ((104, "큰 깃발"), (292, "중간 깃발"), (428, "작은 깃발"))))''',
  '''       post=lambda sh: "".join(txt(*sh((x, 72)), name, 15)
                               for x, name in ((112, "큰 깃발"), (318, "중간 깃발"), (470, "작은 깃발"))))'''),
 # q11: B 이름표를 오른쪽 정칠각형 안 모서리 쪽으로
 ('''ltext(B[0] + 9, B[1] + 14, "B"), ltext(C[0] + 13, C[1] + 8, "C"),''',
  '''ltext(B[0] + 15, B[1] - 3, "B"), ltext(C[0] + 13, C[1] + 9, "C"),'''),
 # lint 예외
 ('''LINT_EXEMPT = {}''',
  '''LINT_EXEMPT = {
    # 여섯 칸 그림이라 글자 요소가 61개 — lint 의 픽셀 검수 한도(40)를 넘는다(결함 아님, 육안 검수로 대체).
    "q2": ("텍스트가 픽셀 검수 안전 한도",),
    # 원본 인쇄 그대로 옅은 음영 칸 위의 숫자 — lint 는 음영도 '선 잉크'로 센다.
    "q15": ("라벨-선 겹침: '3'", "라벨-선 겹침: '7'", "라벨-선 겹침: '11'", "라벨-선 겹침: '15'"),
}'''),
]
for a, b in rep:
    assert s.count(a) == 1, a[:60]
    s = s.replace(a, b)
p.write_text(s, encoding="utf-8")
print("patched")
