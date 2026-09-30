# -*- coding: utf-8 -*-
"""성광중2 26-2-중간 self-OCR JSON 생성(세션 비전 판독, API 0원)."""
import json
import os

D = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def T(v):
    return {"type": "text", "value": v}


def E(v):
    return {"type": "equation", "value": v}


def F(desc, bb):
    return {"type": "figure", "value": desc, "bbox": bb}


def ch(*items):
    out = []
    for i, it in enumerate(items, 1):
        if isinstance(it, str):
            it = [E(it)]
        out.append({"number": i, "contents": it})
    return out


def Q(n, s, contents, choices=None, **kw):
    q = {"number": n, "score": s, "contents": contents, "choices": choices or []}
    q.update(kw)
    return q


P = {2: [], 3: [], 4: [], 5: [], 6: []}

# ── p2 ──────────────────────────────────────────────────────────────
P[2].append(Q(1, 2, [
    T("다음 중 "), E(r"\triangle ABC"), T("가 항상 이등변삼각형이 되는 경우가 "),
    T("__아닌__"), T(" 것은?")],
    ch([E(r"\angle A=15^\circ"), T(", "), E(r"\angle C=15^\circ")],
       [E(r"\overline{AB}=6\mathrm{cm}"), T(", "), E(r"\overline{AC}=6\mathrm{cm}")],
       [E(r"\overline{AB}=8\mathrm{cm}"), T(", "), E(r"\angle A=45^\circ")],
       [E(r"\angle A=50^\circ"), T(", "), E(r"\angle C=80^\circ")],
       [E(r"\overline{AB}=6\mathrm{cm}"), T(", "), E(r"\overline{AC}=5\mathrm{cm}"),
        T(", "), E(r"\overline{BC}=5\mathrm{cm}")])))

P[2].append(Q(2, 3, [
    T("그림과 같은 "), E(r"\triangle ABC"), T("에서 "), E(r"\overline{AB}=\overline{AC}"),
    T("이고, "), E(r"\overline{AD}"), T("는 "), E(r"\angle A"),
    T("의 이등분선일 때, 다음 중 옳지 "), T("__않은__"), T(" 것은?"),
    F("이등변삼각형 ABC(A 위, B 좌하, C 우하). A에서 밑변 BC 위의 점 D로 선분 AD(수직, D는 BC 중점). "
      "AB·AC에 같음 표시(두 줄), A의 두 각에 점(•) 표시.", [0.21, 0.43, 0.38, 0.54])],
    ch([E(r"\overline{AD}\perp\overline{BC}")],
       [E(r"\overline{BD}=\overline{CD}")],
       [E(r"\overline{AD}=\overline{BC}")],
       [E(r"\angle B=\angle C")],
       [E(r"\angle ADC=90^\circ")])))

P[2].append(Q(3, 3, [
    T("그림과 같은 "), E(r"\triangle ABC"), T("에서 "), E(r"\angle ABD=\angle CBD"),
    T("이고, "), E(r"\overline{AB}=16\mathrm{cm}"), T(", "), E(r"\overline{CD}=5\mathrm{cm}"),
    T("일 때, "), E(r"\triangle ABD"), T("의 넓이는?"),
    F("∠C=90°인 직각삼각형 ABC(A 위, B 좌하, C 우하, C에 직각 표시). 변 AC 위의 점 D와 B를 이은 선분 BD"
      "(∠B의 이등분선, B의 두 각에 점 표시). AB 위쪽 점선 치수 16cm, DC 오른쪽 점선 치수 5cm.",
      [0.20, 0.71, 0.40, 0.82])],
    ch(r"38\mathrm{cm}^{2}", r"40\mathrm{cm}^{2}", r"42\mathrm{cm}^{2}",
       r"44\mathrm{cm}^{2}", r"46\mathrm{cm}^{2}")))

P[2].append(Q(4, 3, [
    T("폭이 일정한 종이 테이프를 그림과 같이 접었다. "), E(r"\angle DAB=77^\circ"),
    T("일 때, "), E(r"\angle ACB"), T("의 크기는?"),
    F("폭이 일정한 종이 테이프를 선분 AB를 접는 선으로 접은 그림. 위 변 위의 A, 그 오른쪽(점선) D, 아래 변 위의 C·B. "
      "접힌 부분은 AB에서 왼쪽 아래로 내려감(AC 연장선과 B를 지나는 평행선). 오른쪽 원래 부분은 점선. ∠DAB=77° 표시.",
      [0.565, 0.16, 0.835, 0.265])],
    ch(r"20^\circ", r"22^\circ", r"24^\circ", r"26^\circ", r"28^\circ")))

P[2].append(Q(5, 4, [
    T("그림과 같이 "), E(r"\angle B=\angle C"), T("인 이등변삼각형 "), E(r"ABC"),
    T("에 정삼각형 "), E(r"DEF"), T("가 내접해 있다. "), E(r"\angle AFE=63^\circ"), T(", "),
    E(r"\angle CED=41^\circ"), T("일 때, "), E(r"\angle BDF"), T("의 크기는?"),
    F("이등변삼각형 ABC(A 위, B 좌하, C 우하)에 정삼각형 DEF 내접(F는 AB 위, E는 AC 위, D는 BC 위). "
      "F에 ∠AFE=63°, E에 ∠CED=41° 표시.", [0.615, 0.515, 0.81, 0.655])],
    ch(r"48^\circ", r"49^\circ", r"50^\circ", r"51^\circ", r"52^\circ")))

# ── p3 ──────────────────────────────────────────────────────────────
P[3].append(Q(6, 4, [
    T("그림과 같이 "), E(r"\angle B=90^\circ"), T("인 직각삼각형 "), E(r"ABC"),
    T("의 빗변 "), E(r"AC"), T("의 중점을 "), E(r"O"), T("라 하자. "),
    E(r"\angle AOB=52^\circ"), T("일 때, "), E(r"\angle ACB"), T("의 크기는?"),
    F("∠B=90°인 직각삼각형 ABC(A 위, B 좌하, C 우). 빗변 AC의 중점 O와 B를 이은 선분 BO. "
      "AO·OC에 같음 표시, O에 ∠AOB=52°, C의 각은 음영.", [0.205, 0.175, 0.40, 0.255])],
    ch(r"26^\circ", r"28^\circ", r"30^\circ", r"32^\circ", r"34^\circ")))

P[3].append(Q(7, 4, [
    T("그림과 같이 "), E(r"\triangle ABC"), T("와 그 내접원이 점 "), E(r"D, E, F"),
    T("에서 각각 접하고 있으며 "), E(r"\overline{AB}=7\mathrm{cm}"), T(", "),
    E(r"\overline{BC}=10\mathrm{cm}"), T(", "), E(r"\overline{CA}=9\mathrm{cm}"), T("이다. "),
    E(r"\overline{AD}=a\mathrm{cm}"), T(", "), E(r"\overline{CE}=b\mathrm{cm}"),
    T("일 때, "), E(r"2ab"), T("의 값은? (단, "), E(r"a, b"), T("는 상수)"),
    F("삼각형 ABC와 내접원(접점 D는 AB 위, E는 BC 위, F는 CA 위). 점선 치수 AB 7cm, CA 9cm, BC 10cm.",
      [0.175, 0.425, 0.415, 0.545])],
    ch("34", "36", "38", "40", "42")))

P[3].append(Q(8, 5, [
    T("그림에서 점 "), E(r"I"), T(", "), E(r"O"), T("는 각각 "), E(r"\triangle ABC"),
    T("의 내심과 외심이다. "), E(r"\angle BIC=110^\circ"), T(", "), E(r"\angle ACB=62^\circ"),
    T("일 때, "), E(r"\angle IAO"), T("의 크기는?"),
    F("삼각형 ABC(A 위, B 좌하, C 우하)와 내심 I, 외심 O. 선분 AI, AO, BI, BO, CI, CO. "
      "I에 ∠BIC=110°, C에 ∠ACB=62°(화살표 라벨).", [0.205, 0.685, 0.385, 0.83])],
    ch(r"8^\circ", r"9^\circ", r"10^\circ", r"11^\circ", r"12^\circ")))

P[3].append(Q(9, 3, [
    T("그림과 같은 평행사변형 "), E(r"ABCD"), T("에서 점 "), E(r"O"),
    T("는 두 대각선의 교점이고, "), E(r"\overline{BC}=8\mathrm{cm}"), T(", "),
    E(r"\overline{BD}=14\mathrm{cm}"), T(", "), E(r"\angle BCD=120^\circ"), T(", "),
    E(r"\angle ADC=z^\circ"), T("일 때, "), E(r"x+y+z"), T("의 값은?"),
    F("평행사변형 ABCD(A 좌상, D 우상, B 좌하, C 우하)와 대각선 AC·BD의 교점 O. 점선 치수 AD (x+2)cm, "
      "BO (2y-5)cm(화살표), BD 14cm, BC 8cm. C에 120°, D에 z°(음영).", [0.58, 0.17, 0.85, 0.28])],
    ch("42", "60", "66", "72", "75")))

P[3].append(Q(10, 3, [
    T("그림과 같은 "), E(r"\square ABCD"), T("에서 두 대각선의 교점을 "), E(r"O"),
    T("라 할 때, 사각형 "), E(r"ABCD"), T("가 평행사변형이 되기 위한 조건이 "),
    T("__아닌__"), T(" 것은?"),
    F("사각형 ABCD(A 좌상, D 우상, B 좌하, C 우하)와 두 대각선 AC·BD의 교점 O.",
      [0.62, 0.515, 0.83, 0.59])],
    ch([E(r"\triangle AOD\equiv\triangle COB")],
       [E(r"\overline{OA}=\overline{OD}"), T(", "), E(r"\overline{OB}=\overline{OC}")],
       [E(r"\overline{AB}//\overline{DC}"), T(", "), E(r"\overline{AB}=\overline{DC}")],
       [E(r"\overline{AB}=\overline{DC}"), T(", "), E(r"\overline{AD}=\overline{BC}")],
       [E(r"\angle A=\angle C"), T(", "), E(r"\angle B=\angle D")])))

# ── p4 ──────────────────────────────────────────────────────────────
P[4].append(Q(11, 4, [
    T("그림과 같이 평행사변형 "), E(r"ABCD"), T("의 대각선 "), E(r"AC"), T(" 위에 "),
    E(r"\overline{AP}=\overline{CQ}"), T("인 두 점 "), E(r"P, Q"), T("를 잡을 때, "),
    E(r"\angle PQD=75^\circ"), T(", "), E(r"\angle DPQ:\angle BPQ=2:3"),
    T("이다. 이 때, "), E(r"\angle PBQ"), T("의 크기는?"),
    F("평행사변형 ABCD(A 좌상, D 우상, B 좌하, C 우하)의 대각선 AC 위 두 점 P(A 쪽), Q(C 쪽). "
      "선분 BP, PD, BQ, QD. AP·CQ에 같음 표시, Q에 ∠PQD=75°, B의 ∠PBQ 음영.", [0.19, 0.175, 0.395, 0.27])],
    ch(r"50^\circ", r"52^\circ", r"55^\circ", r"58^\circ", r"60^\circ")))

P[4].append(Q(12, 4, [
    T("그림과 같이 "), E(r"\overline{AB}=13\mathrm{cm}"), T(", "), E(r"\overline{AD}=16\mathrm{cm}"),
    T("인 평행사변형 "), E(r"ABCD"), T("를 꼭짓점 "), E(r"B"), T("가 변 "), E(r"CD"),
    T("의 중점 "), E(r"M"), T("과 겹치도록 접었다. 접는선 "), E(r"AE"), T("와 변 "), E(r"DC"),
    T("의 연장선의 교점을 "), E(r"F"), T("라 할 때, "), E(r"\overline{CF}"), T("의 길이는?"),
    F("평행사변형 ABCD를 AE를 접는 선으로 접어 B가 CD의 중점 M에 온 그림. AB·BE는 점선(접히기 전), "
      "AE 연장선과 DC 연장선의 교점 F. 점선 치수 AD 16cm, AB 13cm. 접힌 부분 음영.", [0.21, 0.445, 0.40, 0.56])],
    ch(r"5\mathrm{cm}", r"5.5\mathrm{cm}", r"6\mathrm{cm}", r"6.5\mathrm{cm}", r"7\mathrm{cm}")))

P[4].append(Q(13, 5, [
    T("그림과 같은 "), E(r"\triangle ABC"), T("의 각 변을 한 변으로 하는 "), E(r"\triangle DBA"),
    T(", "), E(r"\triangle EBC"), T(", "), E(r"\triangle FAC"), T("가 모두 정삼각형이다. "),
    E(r"\angle BAC=100^\circ"), T("일 때, "), E(r"\angle EDA"), T("의 크기는?"),
    F("삼각형 ABC(A 가운데, B 좌하, C 우하)와 정삼각형 DBA(D 왼쪽), EBC(E 위), FAC(F 오른쪽 위). "
      "선분 DE, EF, DA, AF, EB, EC.", [0.18, 0.725, 0.40, 0.84])],
    ch(r"30^\circ", r"33^\circ", r"35^\circ", r"37^\circ", r"40^\circ")))

P[4].append(Q(14, 4, [
    T("그림과 같이 마름모 "), E(r"ABCD"), T("의 한 꼭짓점 "), E(r"A"), T("에서 "),
    E(r"\overline{BC}"), T("에 내린 수선의 발을 "), E(r"F"), T("이라 하자. "),
    E(r"\angle ADB=33^\circ"), T("일 때, "), E(r"\angle x+\angle y"), T("의 값은?"),
    F("마름모 ABCD(A 위, B 좌, C 아래, D 우)와 대각선 AC·BD의 교점 O(직각 표시). A에서 BC에 내린 수선의 발 F"
      "(직각 표시), AF와 BD의 교점 E. D에 33°, E에 ∠y(∠AED), C에 ∠x(∠ACB).", [0.59, 0.17, 0.83, 0.29])],
    ch(r"90^\circ", r"97^\circ", r"100^\circ", r"106^\circ", r"114^\circ")))

P[4].append(Q(15, 3, [
    T("그림과 같은 정사각형 "), E(r"ABCD"), T("에서 "), E(r"\overline{AD}=\overline{AE}"), T(", "),
    E(r"\angle ADE=80^\circ"), T("일 때, "), E(r"\angle ABE"), T("의 크기는?"),
    F("정사각형 ABCD(A 좌상, D 우상, B 좌하, C 우하) 위쪽의 점 E. 선분 AE, DE, BE. AE·AD에 같음 표시, "
      "D에 ∠ADE=80°, B의 ∠ABE 음영.", [0.63, 0.505, 0.815, 0.65])],
    ch(r"30^\circ", r"32^\circ", r"35^\circ", r"42^\circ", r"45^\circ")))

# ── p5 ──────────────────────────────────────────────────────────────
P[5].append(Q(16, 4, [
    T("그림과 같은 평행사변형 "), E(r"ABCD"), T("의 네 내각의 이등분선의 교점을 각각 "),
    E(r"E, F, G, H"), T("라 하고, "), E(r"\square EFGH"), T("의 두 대각선의 교점을 "), E(r"O"),
    T("라 하자. "), E(r"\square EFGH"), T("에 대한 설명 중 옳지 "), T("__않은__"), T(" 것은?"),
    F("평행사변형 ABCD(A 좌상, D 우상, B 좌하, C 우하)의 네 내각의 이등분선이 만드는 사각형 EFGH"
      "(E 왼쪽, F 아래, G 오른쪽, H 위)와 대각선 EG·HF의 교점 O. 각 꼭짓점의 이등분된 두 각에 ×, ∘, △, • 표시.",
      [0.17, 0.18, 0.435, 0.285])],
    ch([E(r"\overline{EG}\perp\overline{HF}")],
       [E(r"\overline{EH}//\overline{FG}")],
       [E(r"\overline{EF}=\overline{HG}")],
       [E(r"\overline{OE}=\overline{OH}")],
       [E(r"\angle HEF=\angle EFG")])))

P[5].append(Q(17, 3, [
    T("그림과 같이 두 삼각기둥이 서로 닮은 도형이고 "), E(r"\overline{AB}"), T("와 "),
    E(r"\overline{GH}"), T("가 서로 대응하는 모서리일 때, 다음 중 옳지 "), T("__않은__"),
    T(" 것은?"),
    F("닮은 두 삼각기둥. 작은 것: 윗면 ABC, 아랫면 DEF, AC 4cm, AD 6cm, DE 4cm, EF x cm. "
      "큰 것: 윗면 GHI, 아랫면 JKL, GI z cm, GJ y cm, JK 6cm, KL 3cm. 숨은 모서리 DF·JL 점선.",
      [0.12, 0.52, 0.455, 0.65])],
    ch([E(r"x+y+z=19")],
       [E(r"\triangle ABC\sim\triangle GHI")],
       [T("닮음비는 "), E(r"2:3"), T("이다.")],
       [E(r"\overline{GJ}"), T("에 대응하는 모서리는 "), E(r"\overline{AD}"), T("이다.")],
       [T("꼭짓점 "), E(r"F"), T("에 대응하는 점은 점 "), E(r"L"), T("이다.")])))

P[5].append(Q(18, 4, [
    T("그림과 같이 크기가 다르고 모양이 똑같은 등대가 있다. 높이가 "), E(r"8\mathrm{m}"),
    T("인 등대 "), E(r"1"), T("개를 색칠하는데 페인트 "), E(r"12"),
    T("통이 필요하다고 할 때, 높이가 "), E(r"12\mathrm{m}"),
    T("인 등대를 색칠하려면 몇 통의 페인트가 필요한가?"),
    F("모양이 같은 두 등대(작은 것 높이 8m, 큰 것 높이 12m, 높이 치수 화살표). 등대에서 빛이 나감.",
      [0.56, 0.19, 0.89, 0.295])],
    ch([E("18"), T("통")], [E("27"), T("통")], [E("32"), T("통")], [E("36"), T("통")],
       [E("40"), T("통")])))

P[5].append(Q(19, 7, [
    T("[서술형 1] 그림과 같이 "), E(r"\angle A=90^\circ"), T("인 "), E(r"\triangle ABC"),
    T("의 세 변의 길이가 각각 "), E(r"\overline{AB}=15\mathrm{cm}"), T(", "),
    E(r"\overline{BC}=17\mathrm{cm}"), T(", "), E(r"\overline{CA}=8\mathrm{cm}"), T("일 때, "),
    E(r"\triangle ABC"), T("의 내접원 "), E(r"I"), T("의 반지름의 길이를 구하시오."),
    F("∠A=90°인 직각삼각형 ABC(A 위, B 좌, C 우, A에 직각 표시)와 내접원(중심 I). "
      "점선 치수 AB 15cm, CA 8cm, BC 17cm.", [0.56, 0.535, 0.885, 0.66])],
    label_type="서술형"))

# ── p6 ──────────────────────────────────────────────────────────────
P[6].append(Q(20, 12, [
    T("[서술형 2] 그림과 같은 "), E(r"\triangle ABC"), T("에 대하여 물음에 답하시오."),
    F("삼각형 ABC(A 위, B 좌하, C 우하)와 내부의 점 P. 선분 PA, PB, PC. "
      "A에 ∠x(∠BAP), B에 ∠y(∠CBP), C에 ∠z(∠ACP).", [0.195, 0.12, 0.40, 0.245])],
    label_type="서술형",
    sub_questions=[
        {"number": 1, "score": 6, "contents": [
            T("(1) 점 "), E(r"P"), T("가 "), E(r"\triangle ABC"), T("의 내심일 때 "),
            E(r"\angle x+\angle y+\angle z"), T("의 크기를 쓰고, 그 이유를 서술하시오.")]},
        {"number": 2, "score": 6, "contents": [
            T("(2) 점 "), E(r"P"), T("가 "), E(r"\triangle ABC"), T("의 외심일 때 "),
            E(r"\angle x+\angle y+\angle z"), T("의 크기를 쓰고, 그 이유를 서술하시오.")]},
    ]))

P[6].append(Q(21, 7, [
    T("[서술형 3] 그림과 같은 평행사변형 "), E(r"ABCD"), T("의 넓이는 "), E(r"256"),
    T("이고, "), E(r"\overline{CE}=\overline{ED}"), T(", "), E(r"\overline{AF}:\overline{FE}=2:1"),
    T("일 때, "), E(r"\square OCEF"), T("의 넓이를 구하시오. (단, 점 "), E(r"O"),
    T("는 두 대각선의 교점이다.)"),
    F("평행사변형 ABCD(A 좌상, D 우상, B 좌하, C 우하)와 대각선 AC·BD의 교점 O. CD의 중점 E, 선분 AE와 BD의 교점 F. "
      "CE·ED에 같음 표시, 사각형 OCEF 음영.", [0.18, 0.69, 0.425, 0.78])],
    label_type="서술형"))

P[6].append(Q(22, 9, [
    T("[서술형 4] 그림과 같은 평행사변형 "), E(r"ABCD"), T("의 각 변의 연장선 위에 "),
    E(r"\overline{AP}=\overline{BQ}=\overline{CR}=\overline{DS}"), T("가 되도록 네 점 "),
    E(r"P, Q, R, S"), T("를 잡을 때, "), E(r"\square PQRS"),
    T("가 어떤 사각형이 되는지 쓰고, 그 이유를 서술하시오."),
    F("평행사변형 ABCD와 각 변의 연장선 위의 점 P(DA 연장), Q(AB 연장), R(BC 연장), S(CD 연장)로 만든 "
      "사각형 PQRS.", [0.58, 0.19, 0.845, 0.29])],
    label_type="서술형"))

for pg, qs in P.items():
    with open(os.path.join(D, "ocr", f"p{pg}_merged.json"), "w", encoding="utf-8") as f:
        json.dump({"header": "", "questions": qs}, f, ensure_ascii=False, indent=1)
tot = sum(q["score"] for qs in P.values() for q in qs)
print("questions", sum(len(v) for v in P.values()), "score", tot)
