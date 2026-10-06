# -*- coding: utf-8 -*-
"""사대부중 중2 25-2-기말 self-OCR JSON 작성(세션 비전 판독, API 0원).

손풀이·채점 표시는 무시하고 인쇄면만 판독. 그림 bbox 는 문항 크롭 기준 비율.
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "ocr"


def T(v):
    return {"type": "text", "value": v}


def E(v):
    return {"type": "equation", "value": v}


def F(desc, bbox):
    return {"type": "figure", "value": desc, "bbox": bbox}


def ch(*items):
    out = []
    for i, it in enumerate(items, 1):
        if isinstance(it, list):
            out.append({"number": i, "contents": it})
        else:
            out.append({"number": i, "contents": [E(it)]})
    return out


def deg(*vals):
    return ch(*[f"{v}^{{\\circ}}" for v in vals])


def fr(*pairs):
    return ch(*[(f"\\frac{{{p[0]}}}{{{p[1]}}}" if isinstance(p, tuple) else str(p)) for p in pairs])


def Q(n, s, contents, choices=None, **kw):
    q = {"number": n, "score": s, "contents": contents}
    if choices:
        q["choices"] = choices
    q.update(kw)
    return q


p1 = [
    Q(1, 3, [T("다음 중 그 확률이 1인 것은?")],
      ch([T("해가 동쪽에서 뜰 확률")],
         [T("어떤 사람의 생일이 2월 31일인 확률")],
         [T("주사위 한 개를 던질 때, 3이하의 눈이 나올 확률")],
         [T("주사위 한 개를 던질 때, 1보다 작은 눈이 나올 확률")],
         [T("동전 두 개를 동시에 던질 때, 적어도 1번은 앞면이 나올 확률")])),
    Q(2, 4, [E("0"), T(", "), E("1"), T(", "), E("2"), T(", "), E("3"), T(", "), E("4"),
             T("의 숫자가 각각 하나씩 적힌 5장의 카드 중에서 세 장을 동시에 뽑아 만들 수 있는 "
               "세 자리 자연수의 개수는?")],
      ch("32", "48", "60", "64", "80")),
    Q(3, 4, [T("모양과 크기가 같은 흰 구슬 6개, 노란 구슬 4개, 파란 구슬 "), E("n"),
             T("개가 들어 있는 주머니에서 구슬을 한 개 꺼낼 때, 파란 구슬일 확률이 "),
             E(r"\frac{1}{3}"), T("이다. 이때 "), E("n"), T("의 값은?")],
      ch("3", "4", "5", "6", "7")),
    # ⚠️ 인쇄 원문 '적어도 한 사람만'(학생이 '만'을 지우고 '이'로 고쳐 씀) — 원문 그대로 전사.
    Q(4, 4, [T("어느 시험에서 "), E("A"), T(", "), E("B"), T(", "), E("C"),
             T(" 세 사람이 합격할 확률은 각각 "), E(r"\frac{1}{2}"), T(", "), E(r"\frac{1}{4}"),
             T(", "), E(r"\frac{3}{5}"), T("이다. 이 시험에서 적어도 한 사람만 합격할 확률은?")],
      fr((3, 40), (1, 8), (1, 4), (3, 4), (17, 20))),
    Q(5, 5, [T("그림은 한 변의 길이가 1인 정육각형 "), E("ABCDEF"), T("이다. 점 "), E("P"),
             T("가 꼭짓점 "), E("A"),
             T("를 출발하여 한 개의 주사위를 두 번 던져서 나온 눈의 수의 합만큼 변을 따라 "
               "화살표 방향으로 움직인다. 점 "), E("P"), T("가 꼭짓점 "), E("D"),
             T("에 위치할 확률은?"),
             F("정육각형 ABCDEF(A 좌상, F 우상, E 오른쪽, D 우하, C 좌하, B 왼쪽). 변 AF 위 A 가까이에 점 P(dot), "
               "AF 위쪽에 A→F 방향 화살표. 변 AB 바깥에 점선 치수 1.", [0.30, 0.33, 0.64, 0.75])],
      fr((1, 12), (1, 6), (1, 4), (1, 3), (1, 2))),
    Q(6, 5, [T("그림에서 점 "), E("I"), T("가 "), E(r"\triangle ABC"), T("의 내심이고, 점 "),
             E("D"), T(", "), E("E"), T("는 "), E(r"\overline{AI}"), T(", "), E(r"\overline{CI}"),
             T("의 연장선이 각각 두 변 "), E("BC"), T(", "), E("AB"), T("와 만나는 점이다. "),
             E(r"\angle AEI=60^{\circ}"), T(", "), E(r"\angle ADC=90^{\circ}"), T("일 때, "),
             E(r"\angle B"), T("의 크기는?"),
             F("삼각형 ABC(A 위, B 좌하, C 우하), 내심 I(dot). AI 의 연장선이 BC 와 만나는 점 D(수선, 직각 표시·90°), "
               "CI 의 연장선이 AB 와 만나는 점 E. ∠AEI=60°(호).", [0.19, 0.29, 0.77, 0.72])],
      deg(30, 34, 38, 40, 42)),
]

p2 = [
    Q(7, 4, [T("그림에서 점 "), E("I"), T("는 "), E(r"\triangle ABC"), T("의 내심이다. "),
             E(r"\angle BAC=30^{\circ}"), T("이고, "), E(r"\angle ABC:\angle ACB=2:3"), T("일 때, "),
             E(r"\angle AIB"), T("의 크기는?"),
             F("삼각형 ABC(A 우상, B 좌하, C 우하 — AC 수직, BC 수평), 내심 I(dot), 선분 IA·IB·IC.",
               [0.36, 0.22, 0.64, 0.83])],
      deg(120, 125, 130, 135, 140)),
    Q(8, 3, [T("그림에서 점 "), E("O"), T("는 "), E(r"\triangle ABC"), T("의 외심이다. "),
             E(r"\angle OAC=25^{\circ}"), T("이고 "), E(r"\angle OBA=20^{\circ}"), T("일 때, "),
             E(r"\angle OBC"), T("의 크기는?"),
             F("삼각형 ABC(A 위, B 좌하, C 우하), 외심 O(dot), 선분 OA·OB·OC. ∠OAC 를 가리키는 지시선 25°(오른쪽 바깥), "
               "∠OBA 를 가리키는 지시선 20°(왼쪽 바깥).", [0.30, 0.23, 0.70, 0.80])],
      deg(25, 30, 35, 40, 45)),
    Q(9, 4, [T("그림과 같이 "), E(r"\angle C=90^{\circ}"), T("인 직각삼각형 "), E("ABC"),
             T("의 외접원 "), E("O"), T("의 반지름의 길이를 "), E("a"), T(", 내접원 "), E("I"),
             T("의 반지름의 길이를 "), E("b"), T("라고 할 때, "), E("a+b"), T("의 값은?"),
             F("직각삼각형 ABC(∠C=90° 직각 표시, B 좌하, C 우하, A 우상)와 외접원(중심 O = AB 의 중점, dot)·"
               "내접원(중심 I, dot). 점선 치수 AB=20, AC=12, BC=16.", [0.30, 0.27, 0.71, 0.78])],
      ch("12", "13", "14", "15", "16")),
    Q(10, 3, [T("항상 서로 닮은 도형인 것을 <보기>에서 고른 것은?"),
              T("<보기> ㄱ. 두 정삼각형 • ㄴ. 두 이등변삼각형 • ㄷ. 두 원뿔대 • ㄹ. 두 정육면체")],
      ch([T("ㄱ, ㄷ")], [T("ㄱ, ㄹ")], [T("ㄴ, ㄷ")], [T("ㄴ, ㄹ")], [T("ㄷ, ㄹ")])),
    Q(11, 4, [E(r"\square ABCD \sim \square HGFE"), T("일 때, 옳은 것은?"),
              F("작은 사각형 ABCD(A 좌상, D 우상, B 좌하, C 우하): AD=2(점선), BC=3(점선), ∠D=100°(호). "
                "큰 사각형 EFGH(E 좌상, H 우상, F 좌하, G 우하): FG=6(점선). 큰 쪽은 작은 쪽을 좌우로 뒤집어 2배.",
                [0.07, 0.14, 0.86, 0.58])],
      ch([E(r"\overline{EH}"), T("의 길이는 5이다.")],
         [E(r"\angle H"), T("의 크기는 "), E(r"100^{\circ}"), T("이다.")],
         [E(r"\overline{AB}"), T("에 대응하는 변은 "), E(r"\overline{HG}"), T("이다.")],
         [T("점 "), E("C"), T("에 대응하는 점은 점 "), E("G"), T("이다.")],
         [E(r"\square ABCD"), T("와 "), E(r"\square HGFE"), T("의 닮음비는 "), E("1:3"), T("이다.")])),
    Q(12, 5, [T("그림과 같이 "), E(r"\angle A=90^{\circ}"), T("인 직각삼각형 "), E("ABC"),
              T("에서 점 "), E("O"), T("는 "), E(r"\overline{BC}"), T("의 중점이다. "),
              E(r"\overline{AD}\perp\overline{BC}"), T(", "), E(r"\overline{DE}\perp\overline{AO}"),
              T("일 때, "), E(r"\overline{AE}"), T("의 길이는?"),
              F("직각삼각형 ABC(∠A=90°, A 위, B 좌하, C 우하). A 에서 BC 에 내린 수선의 발 D(직각 표시), BC 의 중점 O, "
                "선분 AO, D 에서 AO 에 내린 수선의 발 E(직각 표시). 점선 치수 AD=10, BD=5, DC=20.",
                [0.15, 0.24, 0.78, 0.70])],
      fr((13, 2), 7, (15, 2), 8, (17, 2))),
]

p3 = [
    Q(13, 4, [T("그림에서 "), E(r"l\parallel m\parallel n"), T("일 때, "), E("5x+7y"), T("의 값은?"),
              F("평행한 세 수평선 l, m, n(오른쪽에 이름)과 세 직선. 왼쪽 직선(좌하→우상): l~m 사이 7, m~n 사이 5. "
                "가운데 직선(좌상→우하): l~m 사이 x, m~n 사이 6. 오른쪽 직선(좌상→우하): l~m 사이 9, m~n 사이 y. "
                "모두 점선 치수.", [0.17, 0.14, 0.86, 0.78])],
      ch("87", "88", "89", "90", "91")),
    Q(14, 4, [T("그림과 같이 "), E(r"\overline{AD}\parallel\overline{BC}"), T("인 사다리꼴 "),
              E("ABCD"), T("에서 점 "), E("M"), T(", "), E("N"), T("은 각각 "), E(r"\overline{AB}"),
              T(", "), E(r"\overline{DC}"), T("의 중점이다. "), E(r"\overline{BD}"), T(", "),
              E(r"\overline{AC}"), T("와 "), E(r"\overline{MN}"), T("의 교점을 각각 "), E("P"),
              T(", "), E("Q"), T("라고 할 때, "), E(r"\overline{PQ}"), T("의 길이는?"),
              F("사다리꼴 ABCD(A 좌상, D 우상, B 좌하, C 우하), AD=6·BC=10 점선 치수. AB 의 중점 M, DC 의 중점 N, "
                "선분 MN, 대각선 AC·BD. BD∩MN=P, AC∩MN=Q. AM=MB(두 줄 눈금), DN=NC(한 줄 눈금).",
                [0.27, 0.27, 0.74, 0.70])],
      fr(1, (4, 3), (5, 3), 2, (7, 3))),
    Q(15, 4, [T("그림의 "), E(r"\triangle ABC"), T("에서 점 "), E("E"), T(", "), E("F"),
              T("는 각각 "), E(r"\overline{AB}"), T(", "), E(r"\overline{AC}"), T("의 중점이고, 점 "),
              E("G"), T("는 "), E(r"\overline{CE}"), T("와 "), E(r"\overline{BF}"), T("의 교점이다. "),
              E(r"\triangle EBC"), T("의 넓이가 16일 때, "), E(r"\square AEGF"), T("의 넓이는?"),
              F("삼각형 ABC(A 위, B 좌하, C 우하). AB 의 중점 E(AE=EB 두 줄 눈금), AC 의 중점 F(AF=FC 한 줄 눈금), "
                "선분 CE·BF 의 교점 G.", [0.22, 0.27, 0.75, 0.74])],
      fr((32, 3), 11, (34, 3), (35, 3), 12)),
]

S = "서답형"
p3 += [
    Q(16, 6, [T("[서답형 1] 서로 다른 두 개의 주사위를 동시에 던져서 나오는 눈의 수를 각각 "), E("a"),
              T(", "), E("b"), T("라고 할 때, 연립방정식 "),
              E(r"\begin{cases} 2x+ay=4 \\ x+y=2b \end{cases}"),
              T("의 해가 없을 확률을 구하는 과정과 답을 쓰시오.")], label_type=S),
    Q(17, 7, [T("[서답형 2] 그림에서 점 "), E("I"), T("는 정삼각형 "), E("ABC"), T("의 내심이다. "),
              E(r"\overline{AB}\parallel\overline{ID}"), T(", "), E(r"\overline{AC}\parallel\overline{IE}"),
              T("이고 "), E(r"\overline{AC}=12"), T("일 때, "), E(r"\overline{DE}"),
              T("의 길이를 구하는 과정과 답을 쓰시오."),
              F("정삼각형 ABC(A 위, B 좌하, C 우하), 내심 I(dot). BC 위의 점 D, E 와 선분 ID(AB 에 평행, 화살표 1개)·"
                "IE(AC 에 평행, 화살표 2개). AC 에 점선 치수 12.", [0.27, 0.36, 0.68, 0.98])],
      label_type=S),
    Q(18, 7, [T("[서답형 3] 그림에서 점 "), E("O"), T("와 점 "), E("I"), T("가 각각 "),
              E(r"\overline{AB}=\overline{AC}"), T("인 이등변삼각형 "), E("ABC"),
              T("의 외심과 내심이다. "), E(r"\angle BAC=40^{\circ}"), T("일 때, "), E(r"\angle IBO"),
              T("의 크기를 구하는 과정과 답을 쓰시오."),
              F("이등변삼각형 ABC(A 위, B 좌하, C 우하), ∠A=40°(호), AB·AC 두 줄 눈금. 외심 O(dot, 위)·내심 I(dot, 아래), "
                "선분 OB·OC·IB·IC.", [0.30, 0.33, 0.61, 0.93])],
      label_type=S),
]

p4 = [
    Q(19, 6, [T("[서답형 4] 그림과 같이 삼각뿔의 높이가 삼등분이 되도록 밑면에 평행한 두 평면으로 자를 때 "
                "생기는 세 입체도형을 차례로 (가), (나), (다)라고 하자. 입체도형 (다)의 부피가 38일 때, "
                "입체도형 (가)의 부피를 구하는 과정과 답을 쓰시오."),
              F("삼각뿔(꼭짓점 위, 밑면의 세 꼭짓점 좌·우·앞)을 밑면에 평행한 두 평면으로 자른 모습. 뒤쪽 모서리는 점선. "
                "위에서부터 (가), (나), (다) — 오른쪽 이름에서 각 부분으로 화살표.", [0.20, 0.38, 0.78, 0.94])],
      label_type=S),
    Q(20, 6, [T("[서답형 5] 그림에서 "), E(r"\triangle ABC"), T("와 닮은 삼각형을 찾아 기호 "), E("∽"),
              T("를 써서 나타내고, 삼각형의 닮음 이유와 조건을 서술하시오.")],
      label_type=S,
      sub_questions=[
          Q(1, 3, [F("삼각형 ABC(B 좌하, C 우하, A 위)와 그 오른쪽 위의 점 D, 선분 AD·DC. 점선 치수 AB=12, BC=16, "
                     "AC=8, AD=4, DC=6.", [0.13, 0.10, 0.75, 0.37])]),
          Q(2, 3, [F("삼각형 ABC(A 위, B 좌하, C 우하), AB 위의 점 D, BC 위의 점 E, 선분 DE. 점선 치수 AD=2, DB=6, BC=12. "
                     "∠BDE 와 ∠C 에 같은 각 표시(•).", [0.12, 0.67, 0.84, 1.0])]),
      ]),
    Q(21, 8, [T("[서답형 6] 그림에서 점 "), E("G"), T("와 "), E("G'"), T("는 각각 "), E(r"\triangle ABC"),
              T("와 "), E(r"\triangle ACD"), T("의 무게중심이다. "), E(r"\overline{BD}=10"), T("일 때, "),
              E(r"\overline{GG'}"), T("의 길이를 구하는 과정과 답을 쓰시오."),
              F("삼각형 ABD(A 위, B 좌하, D 우하), BD 위의 점 C, BC 의 중점 E, CD 의 중점 F, 선분 AE·AC·AF. "
                "AE 위의 G(dot), AF 위의 G′(dot), 선분 GG′. BD 에 점선 치수 10.", [0.22, 0.32, 0.68, 1.0])],
      label_type=S),
]

pages = ((1, p1), (2, p2), (3, p3), (4, p4))
tot = 0
for n, qs in pages:
    for x in qs:
        tot += x["score"]
        if x.get("sub_questions"):
            assert sum(s["score"] for s in x["sub_questions"]) == x["score"], x["number"]
    (OUT / f"p{n}_merged.json").write_text(
        json.dumps({"header": "", "questions": qs}, ensure_ascii=False, indent=1), encoding="utf-8")
mc = sum(x["score"] for _, qs in pages for x in qs if x.get("choices"))
print("questions", sum(len(qs) for _, qs in pages), "score", tot, "선택형", mc, "서답형", tot - mc)
assert tot == 100 and mc == 60
