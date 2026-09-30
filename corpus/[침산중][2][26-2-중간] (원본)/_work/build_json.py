# -*- coding: utf-8 -*-
import json, os
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def T(v): return {"type": "text", "value": v}
def E(v): return {"type": "equation", "value": v}
def EB(v): return {"type": "equation_block", "value": v}
def F(v, bb): return {"type": "figure", "value": v, "bbox": bb}


def ch(*items):
    out = []
    for i, it in enumerate(items, 1):
        if isinstance(it, str):
            it = [E(it)]
        out.append({"number": i, "contents": it})
    return out


def Q(n, s, contents, choices=None, **kw):
    q = {"number": n, "score": s, "contents": contents}
    if choices is not None:
        q["choices"] = choices
    q.update(kw)
    return q


p1 = [
    Q(1, 3, [T("점 "), E("(4,\\ -7)"), T("을 지나고, "), E("y"), T("축과 평행한 직선의 방정식은?")],
      ch("x=4", "x=-3", "x=-7", "y=-7", "y=4x-7")),
    Q(2, 3, [T("그림과 같이 "), E("\\overline{AB}=\\overline{AC}"), T("인 "), E("\\triangle ABC"),
             T("에서 "), E("\\angle A"), T("의 이등분선과 "), E("\\overline{BC}"),
             T("의 교점을 D라고 하자. "), E("\\angle BAD=38^{\\circ}"), T(", "),
             E("\\overline{DB}=5\\mathrm{cm}"), T("일 때, "), E("x+y"), T("의 값은?"),
             F("이등변삼각형 ABC(꼭짓점 A 위, 밑변 BC). A에서 BC 위의 점 D까지 선분 AD. "
               "∠BAD=38° 호 표시, ∠C 에 y° 호 표시. AB·AC 에 같음 표시(두 줄). "
               "BD 5cm·DC x cm 점선 치수.", [0.1, 0.59, 0.45, 0.76])],
      ch("43", "47", "53", "57", "63")),
    Q(3, 4, [T("일차방정식 "), E("3x+y-2=0"), T("의 그래프의 기울기를 "), E("a"), T(", "),
             E("y"), T("절편을 "), E("b"), T("라고 할 때, "), E("ab"), T("의 값은?")],
      ch("-6", "-3", "1", "3", "6")),
    Q(4, 4, [T("일차방정식 "), E("ax+by+c=0"), T("의 그래프가 제2사분면을 지나지 "),
             T("__않는__"), T(" 경우는?")],
      ch("a>0,\\ b>0,\\ c>0", "a>0,\\ b<0,\\ c>0", "a>0,\\ b<0,\\ c<0",
         "a<0,\\ b>0,\\ c<0", "a<0,\\ b<0,\\ c<0")),
    Q(5, 4, [T("연립방정식 "), E("\\begin{cases} x-ay=-1 \\\\ 2x+y=b \\end{cases}"),
             T("의 해를 구하기 위해 두 일차방정식의 그래프를 각각 그린 것이다. 이때, 상수 "),
             E("a,\\ b"), T("에 대하여 "), E("a-b"), T("의 값은?"),
             F("좌표평면. 두 직선이 점 (-3, 1)에서 만남(점선으로 x축 -3, y축 1 표시). "
               "가파른 직선(기울기 -2)과 완만한 직선(기울기 -1/2). 원점 O.",
               [0.6, 0.64, 0.83, 0.75])],
      ch("-7", "-5", "-3", "3", "5")),
]

p2 = [
    Q(6, 4, [T("두 직선 "), E("4x-3y-2=0"), T(", "), E("ax+6y+b=0"),
             T("가 두 개 이상의 점에서 만날 때, 일차함수 "), E("y=bx+a"),
             T("의 그래프의 "), E("x"), T("절편을 구하면? (단, "), E("a,\\ b"), T("는 상수)")],
      ch("-2", "-\\frac{1}{2}", "\\frac{1}{2}", "2", "4")),
    Q(7, 4, [T("그림과 같이 "), E("\\overline{AB}=\\overline{AC}"), T("인 이등변삼각형 ABC에서 "),
             E("\\overline{DE}"), T("를 접는 선으로 하여 점 A가 점 C와 만나도록 접었다. "),
             E("\\angle DCB:\\angle DCE=1:2"), T("일 때, "), E("\\angle BDC"), T("의 크기는?"),
             F("이등변삼각형 ABC를 DE(D는 AB 위, E는 AC 위)를 접는 선으로 접어 A가 C에 오게 함. "
               "접히기 전 부분 AD·AE는 점선, 접힌 삼각형 DEC는 회색 음영, 접는 방향 곡선 화살표.",
               [0.3, 0.35, 0.5, 0.45])],
      ch("55^{\\circ}", "67.5^{\\circ}", "75^{\\circ}", "90^{\\circ}", "92.5^{\\circ}")),
    Q(8, 4, [E("\\angle O"), T("의 이등분선 위의 한 점 P에서 두 반직선 OA와 OB에 내린 수선의 발이 각각 A, B이다. "),
             E("\\overline{OA}=8\\mathrm{cm}"), T(", "), E("\\overline{PB}=6\\mathrm{cm}"), T(", "),
             E("\\angle APO=48^{\\circ}"), T("일 때, <보기>에서 옳은 것만을 있는 대로 고른 것은?"),
             F("각 O의 두 반직선 OA(위)·OB(수평), 이등분선 OP. A·B에 직각 표시, "
               "O에 등각 점 표시 두 개, P에 48° 호. OA 8cm·PB 6cm 점선 치수.",
               [0.3, 0.64, 0.5, 0.76]),
             T("<보기> ㄱ. "), E("\\angle POB=52^{\\circ}"), T(" • ㄴ. "),
             E("\\triangle OPA=18\\mathrm{cm}^{2}"), T(" • ㄷ. "), E("\\angle APB=96^{\\circ}"),
             T(" • ㄹ. "), E("\\overline{OB}=8\\mathrm{cm}"), T(" • ㅁ. "),
             E("\\triangle OPA\\equiv\\triangle OPB")],
      ch([T("ㄱ, ㄷ")], [T("ㄴ, ㅁ")], [T("ㄱ, ㄴ, ㄷ")], [T("ㄴ, ㄹ, ㅁ")], [T("ㄷ, ㄹ, ㅁ")])),
    Q(9, 4, [E("\\angle C=\\angle D=90^{\\circ}"), T("이고, "), E("\\overline{CA}=\\overline{DB}"),
             T("인 두 직각삼각형 ABC와 ABD의 빗변 AB가 겹치도록 놓았다. "),
             E("\\angle DAB=37^{\\circ}"), T("일 때, "), E("\\angle DBC"), T("의 크기는?"),
             F("공통 빗변 AB(수평) 위로 직각삼각형 ABC(C 직각, 왼쪽 위)와 ABD(D 직각, 오른쪽 위). "
               "AD와 BC의 교점 E. AC·DB 같음 표시(두 줄), A에 37° 호.",
               [0.61, 0.13, 0.81, 0.21])],
      ch("13^{\\circ}", "16^{\\circ}", "18^{\\circ}", "20^{\\circ}", "26^{\\circ}")),
    Q(10, 4, [E("\\angle B=90^{\\circ}"), T("인 직각삼각형 ABC에서 "), E("\\overline{AB}=\\overline{AD}"),
              T("이고, "), E("\\overline{AC}\\perp\\overline{ED}"), T("이다. "),
              E("\\overline{AB}=5\\mathrm{cm}"), T(", "), E("\\overline{BC}=12\\mathrm{cm}"), T(", "),
              E("\\overline{CA}=13\\mathrm{cm}"), T("일 때, 삼각형 DEC의 둘레의 길이는?"),
              F("직각삼각형 ABC(B 직각, AB 세로, BC 가로). D는 AC 위(D 직각), E는 BC 위, 선분 AE·DE. "
                "AB 5cm·BC 12cm·CA 13cm 점선 치수.", [0.58, 0.43, 0.75, 0.53])],
       ch([E("18\\mathrm{cm}")], [E("20\\mathrm{cm}")], [E("22\\mathrm{cm}")],
          [E("24\\mathrm{cm}")], [E("25\\mathrm{cm}")])),
    Q(11, 4, [E("\\angle B=90^{\\circ}"), T("이고, "), E("\\overline{AM}=\\overline{CM}"),
              T("인 삼각형 ABC에 대한 설명 중 옳지 "), T("__않은__"), T(" 것은?"),
              F("직각삼각형 ABC(B 직각), 빗변 AC의 중점 M, 선분 BM. AM·CM 같음 표시(두 줄).",
                [0.62, 0.72, 0.8, 0.8])],
       ch([E("\\angle MAB=\\angle MBA")], [E("\\angle AMB=2\\angle MCB")],
          [T("삼각형 ABM은 정삼각형이다.")], [T("삼각형 MBC는 이등변삼각형이다.")],
          [T("점 M은 세 점 A, B, C를 지나는 원의 중심이다.")])),
]

p3 = [
    Q(12, 4, [T("점 O는 "), E("\\triangle ABC"), T("의 외심이고, 점 I는 "), E("\\triangle PQR"),
              T("의 내심이다. 이때, "), E("x-y+z"), T("의 값은?"),
              F("왼쪽: 삼각형 ABC, 외심 O에서 AB·BC·CA에 내린 수선의 발 D·E·F(직각 표시). "
                "AD 11cm·DB x cm·BE 12cm 점선 치수. 오른쪽: 삼각형 PQR, 내심 I에서 PQ·QR·RP에 내린 "
                "수선의 발 L·M·N(직각 표시). QL 8cm·LI 4cm·IM z cm·QM y cm·MR 6cm.",
                [0.07, 0.11, 0.47, 0.24])],
       ch("7", "8", "9", "23", "24")),
    Q(13, 4, [T("점 I는 "), E("\\triangle ABC"), T("의 내심이고 세 점 D, E, F는 각각 내접원과 "),
              E("\\overline{AB}"), T(", "), E("\\overline{BC}"), T(", "), E("\\overline{CA}"),
              T("의 접점이다. "), E("\\overline{BD}=x\\mathrm{cm}"), T(", "),
              E("\\overline{CF}=y\\mathrm{cm}"), T("일 때, "), E("xy"), T("의 값은?"),
              F("삼각형 ABC와 내접원(중심 I), 접점 D(AB)·E(BC)·F(CA). AB 6cm·CA 11cm·BC 10cm 점선 치수.",
                [0.16, 0.41, 0.46, 0.52])],
       ch("\\frac{25}{2}", "16", "\\frac{75}{4}", "21", "25")),
    Q(14, 5, [T("점 O는 "), E("\\triangle ABC"), T("의 외심이고 "), E("\\angle B=52^{\\circ}"),
              T("일 때, "), E("\\angle DAC"), T("의 크기는?"),
              F("삼각형 ABC, 외심 O. A에서 O를 지나 BC 위의 점 D까지 선분 AD. B에 52° 호, A에 ∠DAC 호.",
                [0.2, 0.72, 0.43, 0.81])],
       ch("30^{\\circ}", "32^{\\circ}", "34^{\\circ}", "36^{\\circ}", "38^{\\circ}")),
    Q(15, 5, [T("점 I는 "), E("\\triangle ABC"), T("의 내심이고 "), E("\\angle AIC=111^{\\circ}"),
              T("일 때, "), E("\\angle ADI"), T("와 "), E("\\angle CEI"), T("의 크기의 합은?"),
              F("삼각형 ABC, 내심 I. C에서 AB 위의 점 D로, A에서 BC 위의 점 E로 각의 이등분선. "
                "I에 111°(∠AIC) 호, D에 ∠ADI 호, E에 ∠CEI 호.", [0.55, 0.1, 0.9, 0.26])],
       ch("133^{\\circ}", "136^{\\circ}", "143^{\\circ}", "146^{\\circ}", "153^{\\circ}")),
    Q(16, 5, [T("네 일차방정식 "), E("4x-3y-24=0"), T(", "), E("2y+8=0"), T(", "), E("x=0"), T(", "),
              E("y=-2"), T("의 그래프로 둘러싸인 부분을 "), E("x"),
              T("축을 축으로 한 바퀴 회전시킬 때 생기는 입체도형의 부피는?")],
       ch("40\\pi", "42\\pi", "44\\pi", "46\\pi", "48\\pi")),
]

p4 = [
    Q(17, 10, [T("[서술형 1] 그림과 같이 두 직선 "), E("2x+y-8=0"), T(", "), E("x-y+2=0"),
               T("과 "), E("x"), T("축으로 둘러싸인 도형의 넓이를 <조건>에 맞게 구하시오."),
               F("좌표평면. 직선 x-y+2=0(오른쪽 위로)과 2x+y-8=0(오른쪽 아래로), x축으로 둘러싸인 "
                 "삼각형 음영. 원점 O, 직선 식 라벨.", [0.15, 0.2, 0.42, 0.33]),
               T("<조건> • 두 직선의 교점의 좌표를 구할 것 • "), E("x"),
               T("축과 만나는 점의 좌표를 각각 구할 것 • 도형의 넓이를 구하는 식을 서술할 것")],
      label_type="서술형"),
    Q(18, 8, [T("[서술형 2] 그림과 같은 "), E("\\angle A=36^{\\circ}"), T(", "),
              E("\\overline{AB}=\\overline{AC}"), T("인 "), E("\\triangle ABC"), T("에서 "),
              E("\\angle B"), T("의 이등분선과 "), E("\\overline{AC}"), T("의 교점을 D라고 하자. "),
              E("\\overline{AB}=8\\mathrm{cm}"), T(", "), E("\\overline{BC}=5\\mathrm{cm}"),
              T("일 때, "), E("\\overline{DC}"), T("의 길이를 <조건>에 맞게 구하시오."),
              F("이등변삼각형 ABC(A 위, 꼭지각 36° 호). ∠B의 이등분선 BD(D는 AC 위), B에 등각 점 두 개. "
                "AB 8cm·BC 5cm 점선 치수.", [0.18, 0.62, 0.45, 0.8]),
              T("<조건> • "), E("\\angle ABD"), T(", "), E("\\angle BCD"), T(", "), E("\\angle BDC"),
              T("의 크기를 구할 것 • "), E("\\triangle ABD"), T("와 "), E("\\triangle BCD"),
              T("가 무슨 삼각형인지 서술할 것 • 문제해결에 사용한 도형의 정의 또는 성질을 서술할 것")],
      label_type="서술형"),
    Q(19, 8, [T("[서술형 3] 그림과 같이 "), E("\\overline{AB}=\\overline{AC}"),
              T("인 직각삼각형 ABC에서 꼭짓점 A를 지나는 직선 "), E("l"),
              T("을 긋고, 두 꼭짓점 B, C에서 직선 "), E("l"),
              T("에 내린 수선의 발을 각각 D, E라고 하자. "), E("\\overline{BD}=20\\mathrm{cm}"), T(", "),
              E("\\overline{CE}=9\\mathrm{cm}"), T("일 때, "), E("\\overline{DE}"),
              T("의 길이를 <조건>에 맞게 구하시오."),
              F("직각이등변삼각형 ABC(A 직각, AC 세로·AB 가로, 같음 표시). A를 지나는 직선 l, "
                "B·C에서 l에 내린 수선의 발 D·E(직각 표시). CE 9cm·BD 20cm 점선 치수.",
                [0.62, 0.17, 0.8, 0.27]),
              T("<조건> • 합동인 두 삼각형을 찾아 기호로 나타내고, 합동인 이유 3가지와 합동조건을 서술할 것 "
                "• 근거를 들어 "), E("\\overline{DE}"), T("의 길이를 구할 것")],
      label_type="서술형"),
    Q(20, 9, [T("[서술형 4] "), E("\\angle A=90^{\\circ}"), T("인 직각삼각형 ABC에서 "),
              E("\\overline{AB}=15"), T(", "), E("\\overline{BC}=17"), T(", "), E("\\overline{AC}=8"),
              T("이다. 직각삼각형 ABC의 외접원의 반지름의 길이를 "), E("R"),
              T(", 내접원의 반지름의 길이를 "), E("r"),
              T("이라 할 때, 외접원의 넓이와 내접원의 넓이의 차를 <조건>에 맞게 구하시오."),
              F("직각삼각형 ABC(A 직각 위, BC 가로 밑변). AB 15·AC 8·BC 17 점선 치수.",
                [0.57, 0.58, 0.8, 0.66]),
              T("<조건> • 근거를 제시하여 "), E("R"), T("과 외접원의 넓이를 구할 것 • 근거를 제시하여 "),
              E("r"), T("과 내접원의 넓이를 구할 것 • 외접원의 넓이와 내접원의 넓이의 차를 구하는 식과 답을 구할 것")],
      label_type="서술형"),
]

os.makedirs(os.path.join(HERE, "ocr"), exist_ok=True)
tot = 0
for i, qs in enumerate([p1, p2, p3, p4], 1):
    tot += sum(q["score"] for q in qs)
    with open(os.path.join(HERE, "ocr", f"p{i}_merged.json"), "w", encoding="utf-8") as f:
        json.dump({"header": "", "questions": qs}, f, ensure_ascii=False, indent=1)
print("total", tot)
