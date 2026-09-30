# -*- coding: utf-8 -*-
"""침산중3 26-2-중간 — 세션 self-OCR JSON 작성(구독 비전 판독, API 0원)."""
import json, os
D = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(D, "ocr")
os.makedirs(OUT, exist_ok=True)


def t(v): return {"type": "text", "value": v}
def e(v): return {"type": "equation", "value": v}
def eb(v): return {"type": "equation_block", "value": v}
def fig(v, b): return {"type": "figure", "value": v, "bbox": b}
def ch(*items):
    out = []
    for i, it in enumerate(items, 1):
        out.append({"number": i, "contents": it if isinstance(it, list) else [e(it)]})
    return out


DEG = "^{\\circ}"
P1 = [
    {"number": 1, "score": 3, "contents": [
        t("그림의 직각삼각형 ABC에서 "), e("\\cos \\mathrm{C}=\\frac{4}{5}"), t("일 때, "),
        e("\\overline{\\mathrm{AC}}"), t("의 길이는?"),
        fig("직각삼각형 ABC(∠B=90°, B 좌하·C 우하·A 위). 변 BC 아래 점선 치수 28 cm. B 직각 표시.",
            [0.163, 0.333, 0.333, 0.438])],
     "choices": ch("31\\mathrm{cm}", "32\\mathrm{cm}", "33\\mathrm{cm}", "34\\mathrm{cm}", "35\\mathrm{cm}")},
    {"number": 2, "score": 4, "contents": [t("계산한 값이 가장 작은 것은?")],
     "choices": ch(
         f"\\sin 30{DEG}-\\cos 30{DEG}\\times \\tan 60{DEG}",
         f"\\tan 45{DEG}\\div \\sin 90{DEG}-\\cos 60{DEG}",
         f"2\\sin 45{DEG}\\times \\tan 60{DEG}\\div \\cos 0{DEG}",
         f"\\frac{{\\sin 60{DEG}}}{{\\cos 30{DEG}}}-\\frac{{\\tan 45{DEG}}}{{\\sin 30{DEG}}}+\\sin 90",
         f"\\cos 0{DEG}\\div \\tan 30{DEG}-\\tan 60{DEG}\\times \\cos 60{DEG}")},
    {"number": 3, "score": 3, "contents": [
        t("그림과 같이 반지름의 길이가 "), e("1"), t("인 부채꼴에서 "),
        e("\\overline{\\mathrm{CD}}\\perp \\overline{\\mathrm{AB}}"), t("일 때, 다음 중 "),
        e("\\overline{\\mathrm{DB}}"), t("의 길이를 나타내는 것은?"),
        fig("중심 A, 반지름 1인 부채꼴 ABC(∠CAB=38°). C에서 AB에 내린 수선의 발 D(직각 표시). AC 위 점선 치수 1.",
            [0.623, 0.192, 0.786, 0.275])],
     "choices": ch(f"1-\\sin 38{DEG}", f"1-\\cos 38{DEG}", f"1-\\tan 38{DEG}",
                   f"1-\\cos 52{DEG}", f"1-\\tan 52{DEG}")},
    {"number": 4, "score": 5, "contents": [
        t("그림의 직각삼각형 ABC에서 변 BC 위의 한 점 D에서 변 AC에 내린 수선의 발을 "), e("\mathrm{E}"), t("라고 하자. "),
        e("\\overline{\\mathrm{DC}}=9"), t(", "), e("\\overline{\\mathrm{CE}}=6"), t(", "),
        e(f"\\angle \\mathrm{{BAE}}=x{DEG}"), t("일 때, "), e(f"\\tan x{DEG}"), t("의 값은?"),
        fig("직각삼각형 ABC(∠B=90°, A 위·B 좌하·C 우하). BC 위 점 D, D에서 AC에 내린 수선의 발 E(직각 표시). ∠A 에 x 표시(음영). 점선 치수 DC=9, EC=6.",
            [0.609, 0.45, 0.75, 0.56])],
     "choices": ch("\\frac{\\sqrt{5}}{2}", "\\frac{\\sqrt{5}}{3}", "\\frac{\\sqrt{5}}{5}",
                   "\\frac{2\\sqrt{5}}{5}", "\\frac{3\\sqrt{5}}{5}")},
    {"number": 5, "score": 5, "contents": [
        e(f"0{DEG}<x<45{DEG}"), t("일 때, "),
        e(f"\\sqrt{{(2\\sin 30{DEG}-\\tan x)^{{2}}}}+\\sqrt{{(\\tan x-\\tan 45{DEG})^{{2}}}}"),
        t("을 간단히 하면?")],
     "choices": ch("-2\\tan x+2", "2", "2\\tan x", "-2\\tan x", "0")},
]

P2 = [
    {"number": 6, "score": 4, "contents": [
        e(f"\\angle \\mathrm{{C}}=90{DEG}"), t("인 직각삼각형 ABC의 꼭짓점 C에서 빗변 AB에 내린 수선의 발을 D라고 할 때, 다음 중 그 값이 "),
        t("__다른__"), t(" 하나는?"),
        fig("직각삼각형 ABC(∠C=90°, A 좌하·C 우하·B 위). C에서 AB에 내린 수선의 발 D. D·C 직각 표시.",
            [0.212, 0.125, 0.389, 0.205])],
     "choices": ch("\\frac{\\overline{\\mathrm{CD}}}{\\overline{\\mathrm{AD}}}",
                   "\\frac{\\overline{\\mathrm{BC}}}{\\overline{\\mathrm{AC}}}",
                   "\\frac{\\overline{\\mathrm{BD}}}{\\overline{\\mathrm{CD}}}",
                   "\\frac{\\overline{\\mathrm{CD}}}{\\overline{\\mathrm{BC}}}",
                   "\\tan \\mathrm{A}")},
    {"number": 7, "score": 5, "contents": [
        t("그림에서 "), e("\\overline{\\mathrm{AC}}\\parallel \\overline{\\mathrm{DE}}"), t("이고, "),
        e("\\overline{\\mathrm{AB}}=6\\mathrm{cm}"), t(", "), e("\\overline{\\mathrm{BC}}=8\\mathrm{cm}"), t(", "),
        e("\\overline{\\mathrm{CE}}=4\\mathrm{cm}"), t(", "), e(f"\\angle \\mathrm{{B}}=60{DEG}"),
        t("일 때, "), e("\\square \\mathrm{ABCD}"), t("의 넓이는?"),
        fig("사각형 ABCD(음영)와 BC 연장선 위 점 E. AC∥DE(화살표 표시), 선분 AE. AB=6 cm·BC=8 cm 점선 치수, CE 4 cm, ∠B=60°.",
            [0.205, 0.425, 0.403, 0.513])],
     "choices": ch("15\\sqrt{2}\\mathrm{cm}^{2}", "16\\sqrt{3}\\mathrm{cm}^{2}", "17\\sqrt{2}\\mathrm{cm}^{2}",
                   "18\\sqrt{3}\\mathrm{cm}^{2}", "19\\sqrt{2}\\mathrm{cm}^{2}")},
    {"number": 8, "score": 4, "contents": [
        e(f"0{DEG}\\leq x\\leq 90{DEG}"), t("일 때, 다음 <보기> 중 옳은 것만을 있는 대로 고른 것은?"),
        t("<보기> ㄱ. $\\sin x$의 값은 $0$에서 $1$까지 증가한다. • ㄴ. $\\cos x$의 값은 $1$에서 $0$까지 감소한다. "
          "• ㄷ. $\\tan x$의 값은 $0$에서 $1$까지 증가한다. • ㄹ. $\\sin 90^{\\circ}>\\cos 90^{\\circ}$")],
     "choices": [{"number": i, "contents": [t(v)]} for i, v in enumerate(
         ["ㄱ, ㄴ, ㄷ", "ㄱ, ㄴ, ㄹ", "ㄴ, ㄷ, ㄹ", "ㄱ, ㄷ, ㄹ", "ㄱ, ㄴ, ㄷ, ㄹ"], 1)]},
    {"number": 9, "score": 5, "contents": [
        t("그림과 같이 "), e("\\overline{\\mathrm{AD}}\\parallel \\overline{\\mathrm{BC}}"), t("인 등변사다리꼴 ABCD에서 "),
        e("\\overline{\\mathrm{AB}}=5"), t(", "), e("\\overline{\\mathrm{BC}}=8"), t(", "),
        e("\\overline{\\mathrm{AD}}=4"), t("일 때, "), e("\\tan \\mathrm{C}"), t("의 값은?"),
        fig("등변사다리꼴 ABCD(AD 위·BC 아래). AD 위 점선 치수 4, BC 아래 점선 치수 8, AB 옆 점선 호.",
            [0.637, 0.118, 0.789, 0.2])],
     "choices": ch("\\frac{\\sqrt{21}}{2}", "\\frac{\\sqrt{21}}{3}", "\\frac{\\sqrt{21}}{4}",
                   "\\frac{\\sqrt{21}}{5}", "\\frac{\\sqrt{21}}{6}")},
    {"number": 10, "score": 4, "contents": [
        t("그림 "), e("\\triangle \\mathrm{ABC}"), t("에서 "),
        e("\\overline{\\mathrm{AH}}\\perp \\overline{\\mathrm{BC}}"), t("이고 "),
        e("\\overline{\\mathrm{BH}}=6"), t(", "), e("\\overline{\\mathrm{CH}}=3"), t("일 때, "),
        e("\\frac{\\tan \\mathrm{C}}{\\tan \\mathrm{B}}"), t("의 값을 구하면?"),
        fig("삼각형 ABC, A에서 BC에 내린 수선의 발 H(직각 표시). 점선 치수 BH=6, HC=3.",
            [0.623, 0.445, 0.768, 0.533])],
     "choices": ch("0", "1", "2", "3", "4")},
    {"number": 11, "score": 5, "contents": [
        e(f"a=\\sin 30{DEG}+\\cos 30{DEG}"), t("일 때, "), e("x"), t("에 관한 일차방정식 "),
        e("2ax-1=0"), t("의 해는?")],
     "choices": ch("\\frac{\\sqrt{3}}{2}", "\\frac{\\sqrt{3}+1}{2}", "\\frac{\\sqrt{3}-1}{2}",
                   "\\frac{3\\sqrt{3}}{2}", "\\frac{1}{2}")},
]

P3 = [
    {"number": 12, "score": 4, "contents": [
        t("이차함수 "), e("y=-2x^{2}+12x-7"), t("의 그래프에서 "), e("x"),
        t("의 값이 증가할 때, "), e("y"), t("의 값은 감소하는 "), e("x"), t("의 값의 범위는?")],
     "choices": ch("x<3", "x>3", "x<6", "x>6", "x<9")},
    {"number": 13, "score": 4, "contents": [
        t("그림은 두 이차함수 "), e("y=x^{2}"), t(", "), e("y=x^{2}-5x"), t("의 그래프이다. 직선 "),
        e("l"), t("이 이차함수 "), e("y=x^{2}-5x"), t("의 그래프의 축일 때, 색칠한 부분의 넓이를 구하면?"),
        fig("좌표평면에 두 포물선 y=x²·y=x²-5x(원점 O 공유)와 축 l(x=5/2, 세로 직선). 두 포물선과 y축·직선 l 사이 색칠.",
            [0.166, 0.33, 0.357, 0.463])],
     "choices": ch("\\frac{105}{8}", "\\frac{115}{8}", "\\frac{125}{8}", "\\frac{135}{8}", "\\frac{145}{8}")},
    {"number": 14, "score": 5, "contents": [
        t("<보기>는 이차함수 "), e("y=-\\frac{1}{2}x^{2}-2x+1"),
        t("의 그래프에 대한 학생들의 대화이다. 옳게 설명한 학생을 <보기>에서 있는 대로 찾으면?"),
        t("<보기> ㄱ. 소미: 꼭짓점의 좌표는 $(-2, 1)$이야. • ㄴ. 세정: $y$축과 점 $(0, 1)$에서 만나. "
          "• ㄷ. 채연: 축의 방정식은 $x=-2$ 이야. • ㄹ. 나영: 제$1$사분면은 지나지 않아.")],
     "choices": [{"number": i, "contents": [t(v)]} for i, v in enumerate(
         ["세정, 채연", "채연, 나영", "소미, 세정, 채연", "세정, 채연, 나영", "소미, 세정, 채연, 나영"], 1)]},
    {"number": 15, "score": 5, "contents": [
        t("이차함수 "), e("y=ax^{2}+bx+3"), t("의 그래프가 그림과 같을 때, 일차함수 "),
        e("y=ax+b"), t("의 그래프가 지나지 "), t("__않는__"), t(" 사분면은? (단, "),
        e("a"), t(", "), e("b"), t("는 수)"),
        fig("아래로 볼록한 포물선. y절편 3(점), x축 양의 부분과 만나고 꼭짓점은 제4사분면.",
            [0.665, 0.12, 0.789, 0.203])],
     "choices": [{"number": 1, "contents": [t("제"), e("1"), t("사분면")]},
                 {"number": 2, "contents": [t("제"), e("2"), t("사분면")]},
                 {"number": 3, "contents": [t("제"), e("3"), t("사분면")]},
                 {"number": 4, "contents": [t("제"), e("4"), t("사분면")]},
                 {"number": 5, "contents": [t("제"), e("1"), t("사분면, 제"), e("3"), t("사분면")]}]},
    {"number": 16, "score": 5, "contents": [
        t("그림에서 점 C, D는 포물선 "), e("y=-x^{2}+4x"),
        t(" 위의 점이고, 사각형 ABCD는 정사각형일 때, "), e("\\square \\mathrm{ABCD}"), t("의 넓이는?"),
        fig("포물선 y=-x²+4x 와 정사각형 ABCD(A·B는 x축 위, C·D는 포물선 위).",
            [0.531, 0.398, 0.849, 0.558])],
     "choices": ch("3-\\sqrt{5}", "4-6\\sqrt{5}", "20-7\\sqrt{5}", "24-8\\sqrt{5}", "28-9\\sqrt{5}")},
]

P4 = [
    {"number": 17, "score": 7, "label_type": "서술형", "contents": [
        t("[서술형 1] 이차함수의 그래프가 그림과 같을 때, 이 이차함수의 식 "), e("y=ax^{2}+bx+c"),
        t("을 구하시오. (단, "), e("a"), t(", "), e("b"), t(", "), e("c"), t("는 수)"),
        fig("위로 볼록한 포물선. 꼭짓점 (2, 6)(점선으로 y축 6·x축 2 표시), x축과 x=5 에서 만남.",
            [0.212, 0.305, 0.372, 0.423])]},
    {"number": 18, "score": 7, "label_type": "서술형", "contents": [
        t("[서술형 2] 이차함수 "), e("y=ax^{2}-2ax+b"), t("의 그래프가 점 "), e("(-1, 12)"),
        t("을 지나고, 이 그래프의 꼭짓점이 일차함수 "), e("y=-2x+8"),
        t("의 그래프 위의 점일 때, 두 수 "), e("a"), t(", "), e("b"), t("의 값을 각각 구하시오.")]},
    {"number": 19, "score": 8, "label_type": "서술형", "contents": [
        t("[서술형 3] 다음 그림과 같은 직각삼각형 ABC와 DBC에서 "),
        e(f"\\angle \\mathrm{{ACB}}=45{DEG}"), t(", "), e(f"\\angle \\mathrm{{BDC}}=60{DEG}"), t(", "),
        e("\\overline{\\mathrm{CD}}=10"), t("일 때, "), e("\\triangle \\mathrm{EBC}"),
        t("의 넓이를 "), t("__삼각비를 이용__"), t("하여 구하시오."),
        fig("직각삼각형 ABC(∠A=90°, ∠ACB=45°)와 DBC(∠C=90°, ∠BDC=60°, CD=10). AC와 BD의 교점 E, 삼각형 EBC 색칠.",
            [0.594, 0.14, 0.849, 0.245])]},
    {"number": 20, "score": 8, "label_type": "서술형", "contents": [
        t("[서술형 4] 영수는 자전거를 타고 직선도로를 따라가다가 물웅덩이를 피하기 위해 다음 그림과 같이 길을 돌아갔다. "
          "이때, 영수가 원래 직선 경로로 가는 것보다 몇 "), e("\mathrm{m}"), t(" 더 갔는지 "),
        t("__삼각비를 이용__"), t("하여 구하시오."),
        fig("직선도로 A→C(점선, 중간 물웅덩이). A에서 30° 방향으로 B까지 100 m, B에서 C로 꺾음(AB 연장선과 BC 사이 75°). 왼쪽에 자전거 탄 영수.",
            [0.552, 0.518, 0.885, 0.608])]},
]

for n, qs in enumerate([P1, P2, P3, P4], 1):
    with open(os.path.join(OUT, f"p{n}_merged.json"), "w", encoding="utf-8") as f:
        json.dump({"header": "", "questions": qs}, f, ensure_ascii=False, indent=1)
tot = sum(q["score"] for qs in (P1, P2, P3, P4) for q in qs)
print("questions", sum(len(q) for q in (P1, P2, P3, P4)), "score", tot)
