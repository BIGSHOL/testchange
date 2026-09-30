# -*- coding: utf-8 -*-
"""성광중3 26-2-중간 self-OCR JSON 빌더 (세션 비전 판독, API 0원)."""
import json, os

T = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def t(v):
    return {"type": "text", "value": v}


def e(v):
    return {"type": "equation", "value": v}


def fig(desc, bbox):
    return {"type": "figure", "value": desc, "bbox": bbox}


def ch(*vals):
    """선택지 — 각 값은 equation 문자열 또는 블록 리스트."""
    out = []
    for i, v in enumerate(vals, 1):
        out.append({"number": i, "contents": v if isinstance(v, list) else [e(v)]})
    return out


def q(n, s, contents, choices):
    return {"number": n, "score": s, "contents": contents, "choices": choices}


P = {1: [], 2: [], 3: [], 4: []}

# ── p1 ──
P[1].append(q(1, 2, [
    t("그림과 같이 반지름의 길이가 "), e("4"), t("인 원 O에 내접하는 직각삼각형 ABC에서 "),
    e("\\overline{BC} = 6"), t("일 때, "), e("\\tan A"), t("의 값은?"),
    fig("원 O에 내접하는 직각삼각형 ABC(∠C=90°). 지름 AB(중심 O 지남), BC=6(아래 점선 치수), B~O 점선 치수 4.",
        [0.2, 0.225, 0.37, 0.33]),
], ch("\\frac{3\\sqrt{7}}{7}", "\\frac{\\sqrt{7}}{4}", "\\frac{2}{3}", "\\frac{\\sqrt{7}}{3}", "\\frac{\\sqrt{13}}{3}")))

P[1].append(q(2, 3, [
    t("그림과 같이 좌표평면 위의 원점 O를 중심으로 하고 반지름의 길이가 "), e("1"),
    t("인 사분원에서 "), e("\\overline{BD}"), t("의 길이를 삼각비의 표를 이용하여 구하면?"),
    fig("좌표평면 제1사분면의 반지름 1인 사분원. 원 위의 점 A(y좌표 0.4848, y축까지 점선), A에서 x축에 내린 수선의 발 B, "
        "D(1,0), 직선 OA의 연장이 x=1과 만나는 점 C, CD⊥x축. B·D에 직각 표시.",
        [0.2, 0.495, 0.40, 0.63]),
    {"type": "table", "value": "", "rows": [
        ["각도", "사인(sin)", "코사인(cos)", "탄젠트(tan)"],
        ["28°", "0.4695", "0.8829", "0.5317"],
        ["29°", "0.4848", "0.8746", "0.5543"],
        ["30°", "0.5000", "0.8660", "0.5774"],
    ]},
], ch("0.1255", "0.1254", "0.1253", "0.1252", "0.1251")))

P[1].append(q(3, 4, [
    t("[보기]에서 옳은 것만을 있는 대로 고른 것은?"),
    t("<보기> ㄱ. "),
    e("(1-\\cos 45\\degree - \\sin 30\\degree)(1+\\sin 45\\degree - \\cos 60\\degree)"),
    t("의 값은 "), e("-\\frac{1}{4}"), t("이다. • ㄴ. "),
    e("\\sin^{2}30\\degree + \\cos^{2}30\\degree + \\sin^{2}45\\degree + \\cos^{2}45\\degree + \\sin^{2}60\\degree + \\cos^{2}60\\degree"),
    t("의 값은 "), e("3"), t("이다. • ㄷ. "),
    e("2\\sin^{2}x + \\sin x - 1 = 0"), t("일 때, "), e("\\tan x"), t("의 값은 "),
    e("\\frac{\\sqrt{3}}{3}"), t("이다. (단, "), e("0\\degree \\leq x \\leq 90\\degree"), t(")"),
], ch([t("ㄴ")], [t("ㄱ, ㄴ")], [t("ㄱ, ㄷ")], [t("ㄴ, ㄷ")], [t("ㄱ, ㄴ, ㄷ")])))

P[1].append(q(4, 4, [
    t("그림과 같이 "), e("\\angle C = 90\\degree"), t("인 직각삼각형 ABC에서 "),
    e("\\angle B = 30\\degree"), t("이고 "), e("\\overline{BC} = 4\\sqrt{3} \\mathrm{cm}"),
    t("일 때, 내접원 I의 반지름의 길이는?"),
    fig("∠C=90°, ∠B=30°인 직각삼각형 ABC(B 왼쪽 아래, C 오른쪽 아래, A 오른쪽 위)와 내접원 I. BC 아래 점선 치수 4√3 cm, B에 30°, C에 직각 표시.",
        [0.58, 0.395, 0.83, 0.515]),
], ch("\\sqrt{3}", "\\sqrt{3}-1", "2\\sqrt{3}-2", "2\\sqrt{3}", "2\\sqrt{3}-3")))

P[1].append(q(5, 5, [
    t("그림과 같은 직각삼각형 ABC에서 "),
    e("\\overline{AB} = \\overline{BD} = \\overline{DC}"), t(", "),
    e("\\overline{AD} = \\sqrt{2}"), t("일 때, "), e("\\cos x"), t("의 값은?"),
    fig("∠B=90°인 직각삼각형 ABC(A 왼쪽 아래, B 오른쪽 아래, C 위). D는 BC 위의 점, AB=BD=DC(같음 표시), AD 점선 √2, ∠DAC=x.",
        [0.64, 0.625, 0.80, 0.80]),
], ch("\\frac{3\\sqrt{5}}{5}", "\\frac{3\\sqrt{5}}{10}", "\\frac{3\\sqrt{10}}{5}", "\\frac{3\\sqrt{10}}{10}", "\\frac{4\\sqrt{15}}{5}")))

# ── p2 ──
P[2].append(q(6, 3, [
    t("그림과 같은 "), e("\\triangle ABC"), t("에서 "), e("\\overline{AB} = 8"), t(", "),
    e("\\angle A = 54\\degree"), t(", "), e("\\angle B = 81\\degree"), t("일 때, "),
    e("\\overline{AC}"), t("의 길이는? (단, "), e("\\sin 54\\degree = 0.8"), t(", "),
    e("\\cos 54\\degree = 0.6"), t(", "), e("\\tan 54\\degree = 1.4"), t("로 계산한다.)"),
    fig("삼각형 ABC(A 위, B 왼쪽 아래, C 오른쪽 아래). AB 왼쪽 점선 치수 8, ∠A=54°.",
        [0.17, 0.18, 0.37, 0.29]),
], ch("8.4", "9.6", "11.2", "12.8", "16")))

P[2].append(q(7, 4, [
    e("\\triangle ABC"), t("에서 "), e("\\angle B = 45\\degree"), t(", "),
    e("\\angle ACH = 60\\degree"), t(", "), e("\\overline{BC} = 10 \\mathrm{cm}"), t("일 때, "),
    e("\\overline{AH}"), t("의 길이는?"),
    fig("B, C, H가 한 직선 위(왼→오), A에서 BC의 연장선에 내린 수선의 발 H(직각 표시). ∠B=45°, ∠ACH=60°, BC 아래 10 cm.",
        [0.17, 0.41, 0.36, 0.52]),
], ch("3+\\sqrt{3} \\mathrm{cm}", "5(3+\\sqrt{3}) \\mathrm{cm}", "10(3+\\sqrt{3}) \\mathrm{cm}",
      "15(3+\\sqrt{3}) \\mathrm{cm}", "20(3+\\sqrt{3}) \\mathrm{cm}")))

P[2].append(q(8, 3, [
    t("그림과 같이 반지름의 길이가 "), e("4"), t("인 반원에서 색칠한 부분의 넓이는?"),
    fig("지름 AB, 중심 O, 반지름 4인 반원. 원 위의 점 C, 현 AC와 반지름 OC. ∠CAB=30°, A~O 점선 치수 4. 반원에서 삼각형 AOC를 뺀 부분 색칠.",
        [0.16, 0.69, 0.38, 0.79]),
], ch("8\\pi - 4\\sqrt{3}", "18\\pi - 9\\sqrt{3}", "18\\pi + 9\\sqrt{3}", "36\\pi - 18\\sqrt{3}", "36\\pi + 18\\sqrt{3}")))

P[2].append(q(9, 4, [
    t("그림과 같은 "), e("\\triangle ABC"), t("에서 "), e("\\overline{AB} = 6\\sqrt{3} \\mathrm{cm}"), t(", "),
    e("\\overline{AC} = 6 \\mathrm{cm}"), t(", "), e("\\overline{BC} = 12 \\mathrm{cm}"), t(", "),
    e("\\angle B = \\angle ACD = 30\\degree"), t("일 때, "), e("\\triangle BCD"), t("의 넓이는?"),
    fig("삼각형 ABC(B 왼쪽, C 오른쪽, A 위). D는 AB 위의 점, 선분 CD. 삼각형 DBC 색칠. ∠B=30°, ∠ACD=30°, AB 위 점선 치수 6√3 cm, AC 6 cm, BC 12 cm.",
        [0.56, 0.155, 0.84, 0.27]),
], ch("\\frac{16\\sqrt{3}}{3} \\mathrm{cm}^{2}", "8\\sqrt{3} \\mathrm{cm}^{2}", "10\\sqrt{3} \\mathrm{cm}^{2}",
      "12\\sqrt{3} \\mathrm{cm}^{2}", "\\frac{46\\sqrt{3}}{3} \\mathrm{cm}^{2}")))

P[2].append(q(10, 2, [
    t("그림과 같이 원 O의 두 현 AB와 CD가 수직으로 만난다. "),
    e("\\overline{AM} = 8 \\mathrm{cm}"), t(", "), e("\\overline{MB} = 4 \\mathrm{cm}"), t("일 때, "),
    e("\\overline{CD}"), t("의 길이는?"),
    fig("원 O. 지름 AB(가로), 현 CD(세로)가 점 M에서 수직으로 만남. A~M 점선 치수 8 cm, M~B 4 cm.",
        [0.59, 0.555, 0.78, 0.68]),
], ch("4 \\mathrm{cm}", "4\\sqrt{2} \\mathrm{cm}", "8 \\mathrm{cm}", "8\\sqrt{2} \\mathrm{cm}", "4\\sqrt{10} \\mathrm{cm}")))

# ── p3 ──
P[3].append(q(11, 3, [
    t("그림과 같이 중심이 같고 반지름의 길이가 서로 다른 두 원은 "), e("\\triangle ABC"),
    t("의 내접원과 외접원이다. 세 점 D, E, F는 그 접점이다. 내접원의 반지름의 길이가 "), e("2"),
    t("일 때, "), e("\\triangle ABC"), t("의 넓이와 외접원의 넓이의 합은?"),
    fig("정삼각형 ABC와 중심 O가 같은 내접원·외접원. 접점 D(AB), E(BC), F(AC).",
        [0.17, 0.18, 0.36, 0.30]),
], ch("4\\sqrt{3} + 8\\pi", "8\\sqrt{3} + 8\\pi", "8\\sqrt{3} + 16\\pi", "12\\sqrt{3} + 8\\pi", "12\\sqrt{3} + 16\\pi")))

P[3].append(q(12, 4, [
    t("그림과 같이 중심이 같은 두 반원에서 큰 반원의 현 BC가 작은 반원에 접하고 점 E는 접점이다. 두 반원의 반지름의 길이가 각각 "),
    e("5 \\mathrm{cm}"), t(", "), e("3 \\mathrm{cm}"), t("이고, "),
    e("\\overline{CH} \\perp \\overline{AB}"), t("일 때, "), e("\\overline{CH}"), t("의 길이는?"),
    fig("중심 O가 같은 반지름 5, 3인 두 반원(지름 AB 위). 큰 반원의 현 BC가 작은 반원에 점 E에서 접함. OE=3cm, O~B 점선 치수 5cm. C에서 AB에 내린 수선의 발 H(직각 표시).",
        [0.19, 0.56, 0.42, 0.68]),
], ch("\\frac{18}{5} \\mathrm{cm}", "4 \\mathrm{cm}", "\\frac{21}{5} \\mathrm{cm}", "\\frac{24}{5} \\mathrm{cm}", "5 \\mathrm{cm}")))

P[3].append(q(13, 3, [
    t("그림과 같이 "), e("\\square ABCD"), t("가 원 O에 외접하고, "),
    e("\\overline{AD} : \\overline{BC} = 2 : 3"), t("일 때, "), e("\\overline{AD}"), t("의 길이는?"),
    fig("원 O에 외접하는 사각형 ABCD(AD 위, BC 아래). AB 왼쪽 점선 치수 13 cm, CD 오른쪽 12 cm.",
        [0.59, 0.145, 0.80, 0.25]),
], ch("10 \\mathrm{cm}", "12 \\mathrm{cm}", "14 \\mathrm{cm}", "16 \\mathrm{cm}", "18 \\mathrm{cm}")))

P[3].append(q(14, 3, [
    t("그림과 같이 원 O는 직사각형 ABCD의 세 변과 "), e("\\overline{AE}"),
    t("에 접하고 네 점 F, G, H, I는 그 접점이다. "), e("\\overline{AB} = 8 \\mathrm{cm}"), t(", "),
    e("\\overline{AD} = 12 \\mathrm{cm}"), t("일 때, "), e("\\overline{EI}"), t("의 길이는?"),
    fig("직사각형 ABCD(A 왼쪽 위). 원 O가 AD(G), DC(F), BC(I), 선분 AE(H)에 접함. E는 BC 위의 점. AD 위 점선 치수 12cm, AB 왼쪽 8cm.",
        [0.56, 0.535, 0.82, 0.66]),
], ch("1 \\mathrm{cm}", "1.5 \\mathrm{cm}", "2 \\mathrm{cm}", "2.5 \\mathrm{cm}", "3 \\mathrm{cm}")))

# ── p4 ──
P[4].append(q(15, 4, [
    t("그림과 같이 두 직선 PB, PD는 외접하는 두 원 O, O'의 접선이고, 네 점 A, B, C, D는 그 접점이다. "),
    e("\\overline{AB} = 16 \\mathrm{cm}"), t(", "), e("\\overline{PC} = 16 \\mathrm{cm}"),
    t("일 때, 작은 원 O의 넓이는?"),
    fig("점 P에서 그은 두 직선 PB, PD가 외접하는 두 원(작은 원 O 색칠, 큰 원 O')에 접함. 접점 A, C(작은 원), B, D(큰 원). AB 왼쪽 16cm, PC 오른쪽 16cm.",
        [0.2, 0.14, 0.4, 0.31]),
], ch("16\\pi \\mathrm{cm}^{2}", "32\\pi \\mathrm{cm}^{2}", "48\\pi \\mathrm{cm}^{2}", "60\\pi \\mathrm{cm}^{2}", "64\\pi \\mathrm{cm}^{2}")))

P[4].append(q(16, 5, [
    t("그림과 같이 두 점 P, Q는 점 A에서 원 O에 그은 두 접선의 접점이고, 점 D는 "),
    e("\\overline{AO}"), t("가 원 O와 만나는 점이다. 원 위의 점 D를 지나는 접선이 "),
    e("\\overline{AP}"), t(", "), e("\\overline{AQ}"), t("와 만나는 점을 각각 B, C라 하자. "),
    e("\\overline{AC} = 15 \\mathrm{cm}"), t(", "), e("\\overline{CQ} = 9 \\mathrm{cm}"),
    t(" 일 때, 원 O의 반지름의 길이는?"),
    fig("원 O와 원 밖의 점 A. A에서 그은 접선의 접점 P(위), Q(아래, OQ⊥AQ 직각 표시). AO와 원의 교점 D, D에서의 접선이 AP, AQ와 B, C에서 만남. AC 15 cm, CQ 9 cm 점선 치수.",
        [0.15, 0.575, 0.40, 0.69]),
], ch("10 \\mathrm{cm}", "12 \\mathrm{cm}", "14 \\mathrm{cm}", "16 \\mathrm{cm}", "18 \\mathrm{cm}")))

P[4].append(q(17, 5, [
    t("그림과 같이 정사각형 안에 반지름의 길이가 "), e("2 \\mathrm{cm}"),
    t("인 원 5개가 꼭 맞게 들어가도록 하는 정사각형의 한 변의 길이는?"),
    fig("정사각형 안에 반지름 2cm인 원 5개(네 귀퉁이 원은 두 변에 접하고 가운데 원에 접함), 원 모두 색칠.",
        [0.61, 0.12, 0.79, 0.25]),
], ch("(4\\sqrt{2}-4) \\mathrm{cm}", "(4\\sqrt{2}+4) \\mathrm{cm}", "(6-4\\sqrt{2}) \\mathrm{cm}",
      "(6\\sqrt{3}-6) \\mathrm{cm}", "(6\\sqrt{2}+6) \\mathrm{cm}")))

P[4].append(q(18, 4, [
    t("그림과 같이 반지름의 길이가 "), e("4\\sqrt{3} \\mathrm{cm}"),
    t("인 원 O의 원주 위의 점 P는 원의 중심 O에 겹쳐지도록 "), e("\\overline{AB}"),
    t("를 접는 선으로 하여 접었다. "), e("\\overline{PQ} = \\overline{MQ}"), t("일 때, "),
    e("\\triangle APQ"), t("의 넓이는?"),
    fig("원 O에서 현 AB를 접는 선으로 원주 위의 점 P가 중심 O에 겹치도록 접은 그림(접힌 호는 O를 지나고 원래 호는 점선). O, M(AB의 중점), Q, P가 세로로 한 직선 위, 삼각형 APQ 색칠.",
        [0.61, 0.54, 0.82, 0.69]),
], ch("3\\sqrt{3} \\mathrm{cm}^{2}", "4\\sqrt{3} \\mathrm{cm}^{2}", "5\\sqrt{3} \\mathrm{cm}^{2}",
      "6\\sqrt{3} \\mathrm{cm}^{2}", "7\\sqrt{3} \\mathrm{cm}^{2}")))

os.makedirs(os.path.join(T, "ocr"), exist_ok=True)
tot = 0
for p, qs in P.items():
    tot += sum(x["score"] for x in qs)
    with open(os.path.join(T, "ocr", f"p{p}_merged.json"), "w", encoding="utf-8") as f:
        json.dump({"header": "", "questions": qs}, f, ensure_ascii=False, indent=1)
print("questions", sum(len(v) for v in P.values()), "score", tot)
