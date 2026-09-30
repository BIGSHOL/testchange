# -*- coding: utf-8 -*-
"""산격중2 26-2-중간 — 세션 self-OCR JSON 빌더(판독 결과를 코드로 기록)."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]


def T(v):
    return {"type": "text", "value": v}


def E(v):
    return {"type": "equation", "value": v}


def F(desc, bbox):
    return {"type": "figure", "value": desc, "bbox": bbox}


def ch(*items):
    return [{"number": i + 1, "contents": c if isinstance(c, list) else [E(c)]}
            for i, c in enumerate(items)]


def deg(*vals):
    return ch(*[f"{v}^{{\\circ}}" for v in vals])


def q(n, score, contents, choices=None, **kw):
    d = {"number": n, "score": score, "contents": contents, "choices": choices or []}
    d.update(kw)
    return d


P1 = [
    q(1, 3, [T("그림과 같이 "), E(r"\overline{AB}=\overline{AC}"), T("인 이등변삼각형 "),
             E("ABC"), T("에서 "), E(r"\angle A=40^{\circ}"), T("일 때, "), E(r"\angle x"),
             T("의 크기는?"),
             F("이등변삼각형 ABC(AB=AC, 같음 표시), ∠A=40°, 변 AB를 B 너머로 연장, "
               "B에서의 외각 x 표시", [0.30, 0.28, 0.72, 0.72])],
      deg(95, 100, 105, 110, 115)),
    q(2, 5, [T("그림에서 "), E(r"\triangle ABC"), T("와 "), E(r"\triangle DBC"), T("는 각각 "),
             E(r"\overline{AB}=\overline{AC}"), T(", "), E(r"\overline{BC}=\overline{DC}"),
             T("인 이등변삼각형이다. "), E(r"\angle ACD=\angle DCE=52^{\circ}"), T("일 때, "),
             E(r"\angle x"), T("의 크기는?"),
             F("AB=AC 인 이등변삼각형 ABC, BC=DC 인 이등변삼각형 DBC, 변 BC의 연장선 위의 점 E, "
               "∠ACD=∠DCE=52°, ∠DBC 가 아닌 ∠ABD 에 x 표시", [0.33, 0.28, 0.70, 0.86])],
      deg(45, 46, 48, 50, 52)),
    q(3, 3, [E(r"\triangle ABC"), T("에서 "), E(r"\angle B=\angle C"), T("일 때, "), E("x"),
             T("의 값은?"),
             F("삼각형 ABC, ∠B=∠C(점 표시), AC=(x+6) cm, AB=(2x-4) cm 점선 치수",
               [0.33, 0.20, 0.70, 0.72])],
      ch("9", "10", "11", "12", "13")),
    q(4, 3, [T("그림의 두 직각삼각형이 다음 조건을 만족할 때, "),
             E(r"\triangle ABC\equiv\triangle DEF"), T("가 "), T("__아닌__"), T(" 것은?"),
             F("∠C=90° 인 직각삼각형 ABC 와 ∠F=90° 인 직각삼각형 DEF(좌우 대칭 배치)",
               [0.28, 0.16, 0.75, 0.56])],
      ch([E(r"\overline{AB}=\overline{DE},~\overline{BC}=\overline{EF}")],
         [E(r"\overline{AC}=\overline{DF},~\overline{BC}=\overline{EF}")],
         [E(r"\overline{AB}=\overline{DE},~\angle B=\angle E")],
         [E(r"\overline{BC}=\overline{EF},~\angle B=\angle E")],
         [E(r"\angle A=\angle D,~\angle B=\angle E")])),
    q(5, 4, [T("그림과 같이 직각삼각형 "), E("ABC"), T("에서 "), E(r"\angle A"),
             T("의 이등분선과 "), E(r"\overline{BC}"), T("의 교점을 "), E("D"),
             T("라고 할 때, "), E(r"\triangle ABD"), T("의 넓이는?"),
             F("∠C=90° 인 직각삼각형 ABC, AB=20 cm, AC=12 cm, ∠A의 이등분선 AD, DC=6 cm",
               [0.33, 0.24, 0.75, 0.76])],
      ch(r"48\mathrm{cm}^{2}", r"60\mathrm{cm}^{2}", r"80\mathrm{cm}^{2}",
         r"100\mathrm{cm}^{2}", r"120\mathrm{cm}^{2}")),
    q(6, 3, [T("그림에서 점 "), E("O"), T("가 "), E(r"\triangle ABC"), T("의 외심이고 "),
             E(r"\angle OBC=26^{\circ}"), T(", "), E(r"\angle OCA=40^{\circ}"), T("일 때, "),
             E(r"\angle x"), T("의 크기는?"),
             F("외심 O 와 OA·OB·OC, ∠OBC=26°, ∠OCA=40°, ∠OAB=x", [0.33, 0.22, 0.72, 0.78])],
      deg(20, 21, 22, 23, 24)),
]

P2 = [
    q(7, 4, [T("그림과 같이 "), E(r"\triangle ABC"), T("의 외심 "), E("O"), T("에서 "),
             E(r"\overline{AC}"), T("에 내린 수선의 발을 "), E("D"), T("라고 하자. "),
             E(r"\triangle AOC"), T("의 둘레의 길이가 "), E(r"30\mathrm{cm}"),
             T("일 때, 외접원의 넓이는?"),
             F("외심 O 에서 AC 에 내린 수선의 발 D(직각 표시), OA·OC·OD, AD=6 cm 점선 치수",
               [0.30, 0.25, 0.73, 0.66])],
      ch(r"\frac{225}{4}\pi\mathrm{cm}^{2}", r"64\pi\mathrm{cm}^{2}",
         r"\frac{289}{4}\pi\mathrm{cm}^{2}", r"81\pi\mathrm{cm}^{2}",
         r"100\pi\mathrm{cm}^{2}")),
    q(8, 4, [T("그림에서 점 "), E("I"), T("가 "), E(r"\triangle ABC"),
             T("의 내심일 때, 다음 중 옳은 것은?"),
             F("내심 I, I 에서 AB·BC·CA 에 내린 수선의 발 D·E·F(직각 표시), AI·BI·CI, "
               "∠A 양쪽 × 표시, ∠B 양쪽 • 표시", [0.30, 0.17, 0.74, 0.56])],
      ch([E(r"\overline{AD}=\overline{BD}")], [E(r"\overline{BD}=\overline{BE}")],
         [E(r"\overline{IA}=\overline{IB}=\overline{IC}")], [E(r"\angle IBE=\angle ICE")],
         [E(r"\triangle IAF\equiv\triangle ICF")])),
    q(9, 4, [T("그림에서 점 "), E("I"), T("가 "), E(r"\triangle ABC"), T("의 내심이고 "),
             E(r"\angle IBC=30^{\circ}"), T(", "), E(r"\angle ICB=25^{\circ}"), T("일 때, "),
             E(r"\angle x"), T("의 크기는?"),
             F("내심 I 와 IB·IC, ∠IBC=30°, ∠ICB=25°, ∠A=x", [0.30, 0.25, 0.72, 0.78])],
      deg(70, 75, 80, 85, 90)),
    q(10, 5, [E(r"\angle A>90^{\circ}"), T(", "), E(r"\overline{AB}=\overline{AC}"),
              T("인 이등변삼각형 "), E("ABC"), T("의 내심을 "), E("I"), T(", 외심을 "),
              E("O"), T("라 하자. "), E(r"\angle IBO=30^{\circ}"), T("일 때, "),
              E(r"\angle A"), T("의 크기는?"),
              F("둔각 이등변삼각형 ABC, 내심 I 와 BI, 외심 O(변 BC 아래) 와 BO, "
                "∠ABI=∠IBC(• 표시), ∠IBO=30°", [0.20, 0.22, 0.78, 0.79])],
      deg(100, 104, 106, 110, 120)),
    q(11, 3, [T("평행사변형 "), E("ABCD"), T("에서 "), E("x+y"), T("의 값은?"),
              F("평행사변형 ABCD, AD=7 cm, BC=(4x-5) cm 점선 치수, ∠A=y°, ∠D=100°",
                [0.33, 0.24, 0.68, 0.74])],
      ch("81", "82", "83", "84", "85")),
    q(12, 4, [T("평행사변형 "), E("ABCD"), T("에서 "), E(r"\overline{AE}"), T(", "),
              E(r"\overline{DF}"), T("는 각각 "), E(r"\angle A"), T(", "), E(r"\angle D"),
              T("의 이등분선이고 "), E(r"\overline{AB}=15\mathrm{cm}"), T(", "),
              E(r"\overline{AD}=20\mathrm{cm}"), T("일 때, "), E(r"\overline{FE}"),
              T("의 길이는?"),
              F("평행사변형 ABCD, ∠A·∠D 의 이등분선 AE·DF 가 BC 와 E·F 에서 만나고 G 에서 교차, "
                "AB=15 cm, AD=20 cm 점선 치수, 같은 각 표시", [0.36, 0.33, 0.68, 0.80])],
      ch(r"8\mathrm{cm}", r"9\mathrm{cm}", r"10\mathrm{cm}", r"11\mathrm{cm}",
         r"12\mathrm{cm}")),
]

P4 = [
    q(13, 4, [T("다음 중 옳지 "), T("__않은__"), T(" 것은?")],
      ch([T("마름모는 평행사변형이다.")],
         [T("두 대각선의 길이가 같은 마름모는 정사각형이다.")],
         [T("두 대각선의 길이가 같은 사다리꼴은 직사각형이다.")],
         [T("두 대각선이 서로 수직인 직사각형은 정사각형이다.")],
         [T("한 내각의 크기가 "), E(r"90^{\circ}"), T("인 평행사변형은 직사각형이다.")])),
    q(14, 4, [T("평행사변형 "), E("ABCD"), T("에 다음 조건을 추가할 때, 나머지와 "),
              T("__다른__"), T(" 사각형이 되는 것은? (단, 점 "), E("O"),
              T("는 두 대각선의 교점이다.)"),
              F("평행사변형 ABCD 와 두 대각선 AC·BD, 교점 O", [0.30, 0.26, 0.66, 0.56])],
      ch([E(r"\overline{AC}=\overline{BD}")], [E(r"\overline{AB}\perp\overline{AD}")],
         [E(r"\angle DCB=90^{\circ}")], [E(r"\angle BAC=\angle BDC")],
         [E(r"\angle ABD=\angle DBC")])),
    q(15, 3, [T("마름모 "), E("ABCD"), T("에서 "), E(r"\angle x+\angle y"),
              T("의 값은? (단, 점 "), E("O"), T("는 두 대각선의 교점이다.)"),
              F("마름모 ABCD 와 두 대각선(교점 O), ∠ABO=35°, ∠AOB=x, ∠ADO=y",
                [0.32, 0.25, 0.68, 0.75])],
      deg(115, 120, 125, 130, 135)),
    q(16, 4, [T("직사각형 "), E("ABCD"), T("에서 대각선 "), E("AC"), T("의 중점을 "),
              E("O"), T("라고 하고, 대각선 "), E("AC"), T("의 수직이등분선과 "),
              E(r"\overline{AD}"), T(", "), E(r"\overline{BC}"), T("의 교점을 각각 "),
              E("E"), T(", "), E("F"), T("라고 하자. "), E(r"\overline{ED}=6\mathrm{cm}"),
              T(", "), E(r"\overline{BC}=14\mathrm{cm}"), T("일 때, 사각형 "), E("AFCE"),
              T("의 둘레의 길이는?"),
              F("직사각형 ABCD, 대각선 AC 의 중점 O, 수직이등분선 EF(직각 표시), AO=OC(같음 표시), "
                "AF·CE, ED=6 cm, BC=14 cm 점선 치수", [0.20, 0.35, 0.78, 0.82])],
      ch(r"28\mathrm{cm}", r"29\mathrm{cm}", r"30\mathrm{cm}", r"31\mathrm{cm}",
         r"32\mathrm{cm}")),
    q(17, 5, [T("그림에서 "), E(r"\triangle ABD"), T(", "), E(r"\triangle BCE"), T(", "),
              E(r"\triangle ACF"), T("는 "), E(r"\triangle ABC"),
              T("의 세 변을 각각 한 변으로 하는 정삼각형이다. 다음은 "), E(r"\square EDAF"),
              T("가 평행사변형임을 증명하는 과정이다."),
              F("△ABC 의 세 변 위에 정삼각형 ABD·BCE·ACF(E 는 A 와 같은 쪽), "
                "사각형 EDAF 와 선분 BE·EC·DA·AF", [0.58, 0.16, 0.96, 0.37]),
              T("<상자>"),
              E(r"\triangle ABC"), T("와 "), E(r"\triangle DBE"), T("에서 • "),
              E(r"\overline{AB}=\overline{DB}"), T(", "), E(r"\overline{BC}=\overline{BE}"),
              T(", • "), E(r"\angle ABC=60^{\circ}-\boxed{가}=\angle DBE"),
              T(" • 이므로 "), E(r"\triangle ABC\equiv\triangle DBE"),
              T(" • 따라서 "), E(r"\overline{AC}=\overline{DE}"),
              T(" • 이때 "), E(r"\overline{AC}=\overline{AF}"), T("이므로 "),
              E(r"\overline{DE}=\overline{AF}"), T(" ……① • 마찬가지 방법으로 "),
              E(r"\triangle ABC\equiv\boxed{나}"),
              T(" • 따라서 "), E(r"\overline{AB}=\overline{FE}"),
              T(" • 이때 "), E(r"\overline{AB}=\overline{AD}"), T("이므로 "),
              E(r"\overline{AD}=\boxed{다}"), T(" ……② • ①, ②에 의해 "),
              E(r"\square EDAF"), T("는 평행사변형이 된다."),
              T("위의 (가), (나), (다)에 들어갈 것을 바르게 짝지은 것은?")],
      ch(*[[T("(가) "), E(a), T(", (나) "), E(b), T(", (다) "), E(c)] for a, b, c in [
          (r"\angle ABE", r"\triangle FEC", r"\overline{FE}"),
          (r"\angle ABE", r"\triangle ACF", r"\overline{BD}"),
          (r"\angle ABE", r"\triangle FEC", r"\overline{BD}"),
          (r"\angle ADE", r"\triangle ACF", r"\overline{FE}"),
          (r"\angle ADE", r"\triangle FEC", r"\overline{FE}")]])),
]

P3 = [
    q(18, 8, [T("[서답형 1] 그림은 "), E(r"\angle C=90^{\circ}"), T("인 "), E(r"\triangle ABC"),
              T("이다. 물음에 답하시오."),
              F("∠C=90° 인 직각삼각형 ABC(직각 표시), AB=10 cm, AC=8 cm, BC=6 cm 점선 치수",
                [0.33, 0.16, 0.70, 0.53])],
      label_type="서답형",
      sub_questions=[
          q(1, 4, [E(r"\triangle ABC"), T("의 내접원의 반지름을 구하고 이를 이용하여 "
                                          "내접원의 넓이를 구하는 과정을 서술하시오.")]),
          q(2, 4, [E(r"\triangle ABC"), T("의 외심의 위치와 외접원의 넓이를 구하고 "
                                          "그 과정을 서술하시오.")])]),
    q(19, 8, [T("[서답형 2] 평행사변형 "), E("ABCD"),
              T("에서 두 대각선의 길이가 같을 때, 물음에 답하시오."),
              F("직사각형 모양의 평행사변형 ABCD 와 두 대각선 AC·BD", [0.24, 0.20, 0.57, 0.51])],
      label_type="서답형",
      sub_questions=[
          q(1, 4, [E(r"\triangle ABC"), T("와 "), E(r"\triangle DCB"), T("가 합동임을 설명하시오.")]),
          q(2, 4, [T("(1)을 이용하여 "), E(r"\square ABCD"), T("가 직사각형임을 설명하시오.")])]),
    q(20, 10, [T("[서답형 3] 그림에서 "), E(r"\square ABCD"),
               T("가 평행사변형인 이유를 각각 쓰고, 평행사변형의 뜻을 서술하시오. (단, 점 "),
               E("O"), T("는 두 대각선의 교점이다.)"),
               F("평행사변형 네 개: (1) AD=BC=9 cm, AB=DC=7 cm (2) ∠B=∠D=50°, ∠C=130° "
                 "(3) AD∥BC(화살표), AD=BC=4 cm (4) 대각선 교점 O, OA=3 cm, OC=3 cm, "
                 "OB=4 cm, OD=2 cm", [0.01, 0.20, 0.99, 0.68])],
      label_type="서답형",
      sub_questions=[q(1, 2, [T(":")]), q(2, 2, [T(":")]), q(3, 2, [T(":")]),
                     q(4, 2, [T(":")]), q(5, 2, [T("평행사변형의 뜻:")])]),
    q(21, 9, [T("[서답형 4] 정사각형 "), E("ABCD"), T("에서 두 대각선의 교점이 "), E("O"),
              T("이고, "), E(r"\overline{OA}=2\mathrm{cm}"), T("일 때, 물음에 답하시오."),
              F("정사각형 ABCD 와 두 대각선, 교점 O, OA=2 cm 점선 치수",
                [0.35, 0.13, 0.68, 0.38])],
      label_type="서답형",
      sub_questions=[
          q(1, 3, [E(r"\overline{BD}"), T("의 길이를 구하고 이때 사용된 정사각형의 성질을 "
                                          "설명하시오.")]),
          q(2, 3, [E(r"\angle BAO"), T("의 크기를 구하고 그 이유를 설명하시오.")]),
          q(3, 3, [E(r"\square ABCD"), T("의 넓이를 구하시오.")])]),
]

tot = 0
for page, qs in ((1, P1), (2, P2), (3, P3), (4, P4)):
    for x in qs:
        tot += x["score"]
        if x.get("sub_questions"):
            assert sum(s["score"] for s in x["sub_questions"]) == x["score"], x["number"]
    (HERE / "ocr" / f"p{page}_merged.json").write_text(
        json.dumps({"header": "", "questions": qs}, ensure_ascii=False, indent=1),
        encoding="utf-8")
print("score total", tot)
assert tot == 100
