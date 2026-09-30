# -*- coding: utf-8 -*-
"""대구일중3 26-2-중간 self-OCR JSON 생성(세션 비전 판독 결과를 코드로 기록)."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]


def T(s):
    return {"type": "text", "value": s}


def E(s):
    return {"type": "equation", "value": s}


def F(desc, bbox):
    return {"type": "figure", "value": desc, "bbox": bbox}


def CH(*items):
    out = []
    for i, it in enumerate(items, 1):
        blocks = it if isinstance(it, list) else [E(it)]
        out.append({"number": i, "contents": blocks})
    return out


def Q(n, score, contents, choices=None, **kw):
    q = {"number": n, "score": score, "contents": contents}
    if choices:
        q["choices"] = choices
    q.update(kw)
    return q


DEG = r"^{\circ}"

p1 = [
    Q(1, 3, [T("그림과 같은 포물선을 그래프로 갖는 이차함수의 식은?"),
             F("위로 볼록한 포물선. 꼭짓점 (-1, 0)이 x축 위(눈금 -1), y절편 -3(눈금 -3), 원점 O, x축·y축 화살표.",
               [0.30, 0.12, 0.46, 0.23])],
      CH(r"y=-x^{2}-3", r"y=-3(x-1)^{2}", r"y=-3(x+1)^{2}",
         r"y=-(x-1)^{2}-3", r"y=-(x+1)^{2}-3")),
    Q(2, 4, [T("이차함수 "), E(r"y=2(x-1)^{2}-5"), T("의 그래프를 "), E("x"),
             T("축의 방향으로 "), E("n"), T("만큼, "), E("y"), T("축의 방향으로 "), E("m"),
             T("만큼 평행이동하였더니 이차함수 그래프의 꼭짓점의 좌표가 "), E("(3, 2)"),
             T("가 될 때, "), E("n+m"), T("의 값은? (단, "), E("n"), T(", "), E("m"),
             T("는 상수)")],
      CH("5", "6", "7", "8", "9")),
    Q(3, 4, [T("이차함수 "), E(r"y=ax^{2}+q"), T("의 그래프를 "), E("y"),
             T("축 방향으로 "), E("3"), T("만큼 평행이동하였더니 점 "), E("(0, -1)"),
             T("을 지나고 "), E("x"), T("축과 두 점 A, B에서 만난다. "),
             E(r"\overline{\mathrm{AB}}=4"), T("일 때, "), E("4a-q"), T("의 값은? (단, "),
             E("a"), T(", "), E("p"), T("는 상수)")],
      CH("4", "5", "6", "7", "8")),
    Q(4, 4, [T("이차함수 "), E(r"y=2x^{2}-4x+a-1"), T("의 그래프가 "), E("x"),
             T("축과 한 점에서 만날 때, 상수 "), E("a"), T("의 값은?")],
      CH("3", "4", "5", "6", "7")),
    Q(5, 5, [T("그림과 같이 이차함수 "), E(r"y=\frac{1}{2}x^{2}+2x-\frac{5}{2}"),
             T("의 그래프가 "), E("x"), T("축과 만나는 한 점을 A, 꼭짓점을 B, "), E("y"),
             T("축과 만나는 점을 C라고 할 때, 사각형 OABC의 넓이는?"),
             F("아래로 볼록한 포물선 y=½x²+2x-5/2. x축과의 왼쪽 교점 A(-5,0), 꼭짓점 B(-2,-9/2), y절편 C(0,-5/2). 사각형 OABC 색칠, 선분 AB·BC.",
               [0.64, 0.33, 0.85, 0.45])],
      CH(r"\frac{39}{4}", r"\frac{41}{4}", r"\frac{55}{4}", r"\frac{41}{2}", r"\frac{55}{2}")),
    Q(6, 3, [T("그림과 같이 "), E(r"\angle \mathrm{B}=90" + DEG), T("인 직각삼각형 ABC에서 "),
             E(r"\overline{\mathrm{AB}}=2"), T(", "), E(r"\overline{\mathrm{BC}}=1"),
             T("일 때, "), E(r"\sin A"), T("의 값은?"),
             F("직각삼각형 ABC(∠B=90°, B 오른쪽 아래). 밑변 AB=2(점선 치수), 세로 BC=1(점선 치수), 꼭짓점 A 각 표시.",
               [0.67, 0.69, 0.85, 0.765])],
      CH(r"\frac{\sqrt{5}}{5}", r"\frac{\sqrt{3}}{3}", r"\frac{1}{2}",
         r"\frac{2\sqrt{3}}{5}", r"\frac{2\sqrt{5}}{5}")),
]

p2 = [
    Q(7, 4, [T("그림과 같이 "), E(r"\angle \mathrm{C}=90" + DEG), T("인 직각삼각형 ABC에서 "),
             E(r"\overline{\mathrm{BC}}=4"), T("이다. "), E(r"\tan B=\frac{\sqrt{5}}{2}"),
             T("일 때, "), E(r"\overline{\mathrm{AB}}"), T("의 길이는?"),
             F("직각삼각형 ABC(∠C=90°, C 오른쪽 아래, A 위). 밑변 BC=4(점선 치수).",
               [0.22, 0.17, 0.34, 0.24])],
      CH("5", "6", "7", "8", "9")),
    Q(8, 3, [T("다음 식의 값은?"), T("<상자>"),
             E(r"(\cos 0" + DEG + r"-\cos 60" + DEG + r"-\tan 60" + DEG + r")(\sin 90"
               + DEG + r"-\sin 30" + DEG + r"+\tan 60" + DEG + ")")],
      CH(r"-\frac{11}{4}", r"-\frac{9}{4}", "1", r"\frac{9}{4}", r"\frac{11}{4}")),
    Q(9, 3, [T("그림과 같이 반지름의 길이가 "), E("1"), T("인 사분원에서 "),
             E(r"\overline{\mathrm{AB}}"),
             T("의 길이와 같은 삼각비의 값만을 <보기>에서 있는 대로 고른 것은?"),
             F("반지름 1인 사분원 OED(O 왼쪽 아래, E 위, D 오른쪽). 호 위 점 A, A에서 OD에 내린 수선의 발 B, 직선 OA 연장과 D에서의 수직선의 교점 C. ∠AOB=x°, ∠OAB=y°, ∠OCD=z°. O·B·D 직각 표시, OE=1 점선 치수.",
               [0.22, 0.625, 0.355, 0.71]),
             T(r"<보기> ㄱ. \sin x^{\circ} • ㄴ. \cos x^{\circ} • ㄷ. \tan x^{\circ} • ㄹ. \sin y^{\circ} • ㅁ. \cos y^{\circ} • ㅂ. \cos z^{\circ}")],
      CH([T("ㄱ, ㅁ")], [T("ㄴ, ㄹ")], [T("ㄷ, ㅁ")], [T("ㄱ, ㅁ, ㅂ")], [T("ㄴ, ㄹ, ㅂ")])),
    Q(10, 3, [T("[10~12] 삼각비의 표를 이용하여 물음에 답하시오."),
              {"type": "table", "value": "", "rows": [
                  ["각", "사인(sin)", "코사인(cos)", "탄젠트(tan)"],
                  ["33" + DEG, "0.54", "0.84", "0.65"],
                  ["34" + DEG, "0.56", "0.83", "0.67"],
                  ["54" + DEG, "0.81", "0.59", "1.38"],
                  ["55" + DEG, "0.82", "0.57", "1.43"],
                  ["56" + DEG, "0.83", "0.56", "1.48"]]},
              T("그림과 같이 반지름의 길이가 "), E("1"), T("인 사분원에서 "),
              E(r"\overline{\mathrm{AD}}=0.44"), T("이다. "),
              E(r"\angle \mathrm{BOA}=x" + DEG), T(", "), E(r"\overline{\mathrm{AC}}=y"),
              T("라 할 때, "), E("x+y"), T("의 값은?"),
              F("반지름 1인 사분원(O 왼쪽 아래, A 오른쪽). 호 위 점 B, B에서 OA에 내린 수선의 발 D, 직선 OB 연장과 A에서의 수직선의 교점 C. ∠BOA=x, D·A 직각 표시, AC=y·DA=0.44 점선 치수.",
                [0.64, 0.29, 0.78, 0.40])],
      CH("4.07", "6.93", "34.67", "55.38", "57.48")),
    Q(11, 4, [T("그림과 같이 "), E(r"\angle \mathrm{C}=90" + DEG), T("인 직각삼각형 ABC에서 "),
              E(r"\angle \mathrm{A}=55" + DEG), T(", "), E(r"\overline{\mathrm{AB}}=10"),
              T("일 때, "), E(r"\overline{\mathrm{BC}}"), T("의 길이는?"),
              F("직각삼각형 ABC(∠C=90°, C 위). ∠A=55, 빗변 AB=10(점선 치수), BC=x(점선 치수).",
                [0.64, 0.52, 0.79, 0.585])],
      CH("5.7", "6.7", "8.2", "13.8", "14.3")),
    Q(12, 4, [T("그림과 같이 지점 C에서 두 등대 A, B를 바라본 각의 크기는 "), E("33" + DEG),
              T("이고, 등대 B에서 등대 A와 지점 C를 바라본 각의 크기는 "), E("90" + DEG),
              T("이다. 등대 B와 지점 C사이의 거리가 "), E(r"200\mathrm{m}"),
              T("일 때, 두 등대 A, B사이의 거리는? (단, 단위는 m이다.)"),
              F("바다 위 두 등대 A, B와 방파제 끝 지점 C. 삼각형 ABC(∠B=90°), ∠C=33°, BC=200 m(점선 치수).",
                [0.625, 0.74, 0.80, 0.81])],
      CH("100", "108", "112", "130", "168")),
]

p3 = [
    Q(13, 4, [T("그림과 같이 "), E(r"\triangle \mathrm{ABC}"), T("에서 "),
              E(r"\overline{\mathrm{AB}}=5\mathrm{cm}"), T(", "),
              E(r"\overline{\mathrm{AC}}=8\mathrm{cm}"), T("이다. "), E(r"\triangle \mathrm{ABC}"),
              T("의 넓이가 "), E(r"8\sqrt{3}\mathrm{cm}^{2}"), T("일 때, "), E(r"\cos A"),
              T("의 값은? (단, "), E(r"0" + DEG + r"<\angle \mathrm{A}<90" + DEG), T(")"),
              F("색칠한 삼각형 ABC(A 위, B 왼쪽 아래, C 오른쪽 아래). AB=5cm, AC=8cm 점선 치수.",
                [0.23, 0.135, 0.39, 0.21])],
      CH(r"\frac{\sqrt{13}}{10}", r"\frac{\sqrt{13}}{6}", r"\frac{\sqrt{13}}{5}",
         r"\frac{2\sqrt{5}}{7}", r"\frac{2\sqrt{5}}{5}")),
    Q(14, 5, [T("그림과 같이 정사면체의 꼭짓점 A에서 밑면에 내린 수선의 발 H는 "),
              E(r"\triangle \mathrm{BCD}"), T("의 무게중심이다. "),
              E(r"\angle \mathrm{ADH}=x" + DEG), T(", "), E(r"\overline{\mathrm{DH}}=\sqrt{3}"),
              T("라 할 때, "), E(r"\sin x" + DEG), T("의 값은?"),
              F("정사면체 ABCD(A 꼭대기, B 왼쪽, C 앞 아래, D 오른쪽). BD 점선(가려진 모서리), BC 중점 M, 선분 MD 위 무게중심 H, 수선 AH(H 직각 표시), 삼각형 AHD 색칠, ∠ADH=x°.",
                [0.21, 0.415, 0.38, 0.525])],
      CH(r"\frac{\sqrt{3}}{8}", r"\frac{\sqrt{3}}{6}", r"\frac{\sqrt{6}}{6}",
         r"\frac{\sqrt{3}}{3}", r"\frac{\sqrt{6}}{3}")),
    Q(15, 4, [T("그림과 같이 "), E(r"\angle \mathrm{D}=90" + DEG), T("인 직각삼각형 ABD에서 "),
              E(r"\overline{\mathrm{AD}}=2"), T(", "),
              E(r"\overline{\mathrm{AC}}=\overline{\mathrm{BC}}"), T(", "),
              E(r"\angle \mathrm{ACD}=45" + DEG), T("일 때, "), E(r"\tan 22.5" + DEG),
              T("의 값은?"),
              F("직각삼각형 ABD(∠D=90°, A 위 오른쪽). 밑변 BD 위 점 C, 선분 AC. BC·CA 같음 표시(‖), ∠ACD=45°.",
                [0.19, 0.725, 0.39, 0.805])],
      CH(r"3-\sqrt{5}", r"2-\sqrt{3}", r"2-\sqrt{2}", r"\sqrt{2}-1", r"\sqrt{5}-1")),
    Q(16, 5, [T("그림과 같이 "), E(r"\angle \mathrm{B}=90" + DEG), T(", "),
              E(r"\angle \mathrm{C}=45" + DEG), T("인 직각삼각형 ABC에서 "),
              E(r"\overline{\mathrm{BC}}"), T(" 위의 점 D에서 "), E(r"\overline{\mathrm{AC}}"),
              T("에 내린 수선의 발을 E라 하자. "), E(r"\overline{\mathrm{AC}}=6"), T(", "),
              E(r"\angle \mathrm{ADB}=60" + DEG), T("일 때, "), E(r"\overline{\mathrm{DE}}"),
              T("의 길이는?"),
              F("직각이등변삼각형 ABC(∠B=90°, A 위, C 오른쪽). BC 위 점 D, 선분 AD, D에서 AC에 내린 수선 DE(E 직각 표시). ∠ADB=60°, C 각 표시, AC=6 점선 치수.",
                [0.665, 0.135, 0.805, 0.23])],
      CH(r"\sqrt{3}-\sqrt{2}", r"\sqrt{3}-1", "1", r"3-\sqrt{3}", r"3-\sqrt{2}")),
    Q(17, 4, [T("그림과 같이 연못의 양 끝점을 각각 A, B라 하고 연못 바깥의 한 지점을 C라 할 때, "),
              E(r"\overline{\mathrm{AC}}=20\mathrm{m}"), T(", "),
              E(r"\angle \mathrm{A}=75" + DEG), T(", "), E(r"\angle \mathrm{C}=60" + DEG),
              T("이다. 이때 두 지점 A, B 사이의 거리는? (단, 단위는 m이다.)"),
              F("연못 양 끝 A(왼쪽)·B(오른쪽), 연못 아래 지점 C. 삼각형 ABC, AC=20 m 점선 치수, ∠C=60°.",
                [0.65, 0.43, 0.85, 0.54])],
      CH(r"10\sqrt{6}", r"10\sqrt{7}", r"20\sqrt{2}", r"20\sqrt{3}", "40")),
    Q(18, 4, [T("그림과 같이 평행사변형 ABCD에서 "),
              E(r"\overline{\mathrm{AD}}=7\sqrt{2}\mathrm{cm}"), T("이고, "),
              E(r"\overline{\mathrm{AB}}=6\mathrm{cm}"), T(", "),
              E(r"\angle \mathrm{A}=135" + DEG), T("이다. 점 E가 "), E(r"\overline{\mathrm{BC}}"),
              T("의 중점일 때, "), E(r"\triangle \mathrm{BED}"), T("의 넓이는? (단, 단위는 "),
              E(r"\mathrm{m}^{2}"), T("이다.)"),
              F("평행사변형 ABCD(A 왼쪽 위, D 오른쪽 위, B 왼쪽 아래, C 오른쪽 아래). BC 중점 E(같음 표시), 선분 BD·ED, 삼각형 BED 색칠. ∠A=135°, AB=6cm·AD=7√2 cm 점선 치수.",
                [0.66, 0.725, 0.87, 0.80])],
      CH(r"\frac{21\sqrt{2}}{4}", r"\frac{21}{2}", r"\frac{21\sqrt{2}}{2}",
         r"\frac{21\sqrt{6}}{2}", "21")),
]

p4 = [
    Q(19, 8, [T("[서답형 1] 그림과 같이 이차함수의 그래프가 "), E("x"), T("축과 두 점 "),
              E("(1, 0)"), T(", "), E("(7, 0)"), T("에서 만나고, 꼭짓점은 직선 "), E("y=-3"),
              T(" 위에 있다. 이 때, 이차함수의 식 "), E(r"y=ax^{2}+bx+c"),
              T("를 구하시오. (단, "), E("a, b, c"), T("는 상수) (풀이과정을 상세히 적으시오.)"),
              F("아래로 볼록한 포물선. x축과 1, 7에서 만나고 꼭짓점은 직선 y=-3 위(꼭짓점에서 x축까지 세로 선분). 원점 O, 눈금 -3, 직선 y=-3 표기.",
                [0.20, 0.18, 0.38, 0.285])],
      label_type="서답형"),
    Q(20, 8, [T("[서답형 2] 이차방정식 "), E(r"4x^{2}+4x-3=0"),
              T("의 두 근 중에서 큰 근을 "), E(r"\sin A"),
              T("라 할 때, 다음 물음에 답하시오.")],
      label_type="서답형",
      sub_questions=[
          {"number": 1, "score": 3, "contents": [
              T("(1) "), E(r"0" + DEG + r"<\angle \mathrm{A}<90" + DEG), T("일 때, "),
              E(r"\angle \mathrm{A}"), T("의 크기를 구하시오. (풀이과정을 상세히 적으시오.)")]},
          {"number": 2, "score": 5, "contents": [
              T("(2) "),
              E(r"\sqrt{(\cos 60" + DEG + r"+\cos A)^{2}}+\sqrt{(\sin A-\sin 60" + DEG + r")^{2}}"),
              T("의 값을 간단히 구하시오. (풀이과정을 상세히 적으시오.)")]},
      ]),
    Q(21, 8, [T("[서답형 3] 그림과 같이 "), E(r"\overline{\mathrm{AB}}=3\mathrm{cm}"), T(", "),
              E(r"\overline{\mathrm{BC}}=4\mathrm{cm}"), T(", "),
              E(r"\overline{\mathrm{CD}}=2\mathrm{cm}"), T(", "),
              E(r"\overline{\mathrm{DA}}=\sqrt{3}\mathrm{cm}"), T("이고 "),
              E(r"\angle \mathrm{B}=60" + DEG), T(", "), E(r"\angle \mathrm{D}=150" + DEG),
              T("인 "), E(r"\square \mathrm{ABCD}"),
              T("의 넓이를 구하시오. (풀이과정을 상세히 적으시오.)"),
              F("색칠한 사각형 ABCD(A 위, B 왼쪽 아래, C 오른쪽 아래, D 오른쪽 위). AB=3 cm, BC=4 cm, CD=2 cm, DA=√3 cm 점선 치수, ∠B=60°, ∠D=150°.",
                [0.65, 0.15, 0.83, 0.245])],
      label_type="서답형"),
    Q(22, 6, [T("[서답형 4] "), E(r"\overline{\mathrm{AD}}=6"), T(", "),
              E(r"\overline{\mathrm{DC}}=4"),
              T("인 직사각형 ABCD의 두 변 AD, DC의 중점을 각각 M, N이라 하자. "),
              E(r"\angle \mathrm{MBN}=x" + DEG), T("라 할 때, "), E(r"\sin x" + DEG),
              T("의 값을 구하시오. (단, <조건>을 포함하여 풀이과정을 상세히 적으시오.)"),
              F("직사각형 ABCD(A 왼쪽 위, D 오른쪽 위, B 왼쪽 아래, C 오른쪽 아래). AD 중점 M, DC 중점 N, 선분 BM·MN·BN, ∠MBN=x.",
                [0.64, 0.51, 0.84, 0.605]),
              T(r"<조건> ○ $\overline{\mathrm{BM}}$, $\overline{\mathrm{BN}}$의 길이를 각각 구하시오. ○ $\sin x^{\circ}$를 구하는 식을 세우시오.")],
      label_type="서답형"),
]

for n, qs in enumerate([p1, p2, p3, p4], 1):
    (HERE / "ocr" / f"p{n}_merged.json").write_text(
        json.dumps({"header": "", "questions": qs}, ensure_ascii=False, indent=1),
        encoding="utf-8")

tot = 0
for qs in (p1, p2, p3, p4):
    for q in qs:
        tot += q["score"]
print("questions", sum(len(x) for x in (p1, p2, p3, p4)), "score sum", tot)
