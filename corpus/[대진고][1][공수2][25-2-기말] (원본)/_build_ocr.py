# -*- coding: utf-8 -*-
"""대진고 공수2 25-2-기말 — 세션 self-OCR JSON 생성(원본 인쇄면만 판독, 손글씨 제외).

⚠️ 백슬래시가 도구 레이어에서 벗겨지는 사고를 막으려고 **모든 LaTeX 를 raw 문자열**로
적고 json.dump 로 직렬화한다([[bash-heredoc-backslash-trap]]).
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "ocr")
os.makedirs(OUT, exist_ok=True)


def T(v):
    return {"type": "text", "value": v}


def E(v):
    return {"type": "equation", "value": v}


def EB(v):
    return {"type": "equation_block", "value": v}


def F(v, bbox):
    return {"type": "figure", "value": v, "bbox": bbox}


def CH(*items):
    """선택지 — 문자열이면 수식, ('t', s) 면 평문."""
    out = []
    for i, it in enumerate(items, 1):
        if isinstance(it, tuple):
            out.append({"number": i, "contents": [T(it[1])]})
        else:
            out.append({"number": i, "contents": [E(it)]})
    return out


# ───────────────────────── p1: 1~5 ─────────────────────────
p1 = [
    {
        "number": 1, "score": 3.8,
        "contents": [
            T("집합 "), E(r"A = \{-1,\ 0,\ 1\}"), T("에 대하여 집합 "),
            E(r"B = \{a+b \mid a \in A,\ b \in A\}"), T("일 때, "), E("n(B)"),
            T("의 값은?"),
        ],
        "choices": CH("5", "6", "7", "8", "9"),
        "answer": "①", "topic": "집합의 뜻과 표현", "difficulty": "하",
    },
    {
        "number": 2, "score": 3.8,
        "contents": [
            T("정수 "), E("x"), T("에 대하여 조건 "), E("p"), T("가 "),
            E(r"p : x^{2} - 9x - 36 \geq 0"), T("일 때, 조건 ~"), E("p"),
            T("의 진리집합의 원소의 개수는?"),
        ],
        "choices": CH("12", "13", "14", "15", "16"),
        "answer": "③", "topic": "명제와 조건", "difficulty": "하",
    },
    {
        "number": 3, "score": 4,
        "contents": [
            T("두 집합 "), E(r"X = \{-1,\ 0,\ 1,\ 2,\ 3\}"), T("와 "),
            E(r"Y = \{y \mid y는 정수\}"), T("에 대하여 함수 "), E(r"f : X \to Y"),
            T("가 "), E(r"f(x) = (2x^{2}을~5로 나눈 나머지)"),
            T("일 때, 함수 "), E("f"), T("의 치역의 모든 원소의 합은?"),
        ],
        "choices": CH("2", "3", "5", "9", "10"),
        "answer": "③", "topic": "함수", "difficulty": "하",
    },
    {
        "number": 4, "score": 4,
        "contents": [
            T("함수 "), E(r"f(x) = \frac{ax+b}{x+c}"),
            T("의 그래프가 아래 그림과 같을 때, 함수 "), E("y = f(x)"),
            T("와 그 그래프에 대하여 옳은 것만을 <보기>에서 있는 대로 고른 것은?"),
            F("유리함수 y=f(x)의 그래프. 점근선은 x=1/2(세로 점선)과 y=-2(가로 점선). "
              "왼쪽 가지는 점 (0, 1)을 지나 x=1/2 왼쪽에서 위로 발산, 오른쪽 가지는 "
              "y=-2 아래에서 오른쪽으로 접근. y축 눈금 1과 -2, x=1/2 표시.",
              [0.42, 0.10, 0.80, 0.52]),
            T(r"<보기> ㄱ. a+8bc=0 "
              r"• ㄴ. f^{-1}(-5)=1 "
              r"• ㄷ. 직선 y = x - \frac{5}{2}에 대하여 대칭이다. "
              r"• ㄹ. 평행이동에 의하여 y = -\frac{2}{x}의 그래프와 겹쳐진다."),
        ],
        "choices": CH(("t", "ㄱ, ㄴ"), ("t", "ㄱ, ㄴ, ㄷ"), ("t", "ㄱ, ㄴ, ㄹ"),
                      ("t", "ㄱ, ㄷ, ㄹ"), ("t", "ㄴ, ㄷ, ㄹ")),
        "answer": "②", "topic": "유리함수", "difficulty": "중",
    },
    {
        "number": 5, "score": 4.2,
        "contents": [
            T("집합 "), E(r"X = \{1,\ 2,\ 3\}"), T("에 대하여 "), E("X"), T("에서 "),
            E("X"), T("로의 세 함수 "), E("f"), T(", "), E("g"), T(", "), E("h"),
            T("가 다음 조건을 만족시킬 때, "), E("f(3) + g(1) + h(2)"), T("의 값은?"),
            T("<상자> ○ f는 일대일대응, g는 항등함수, h는 상수함수이다. "
              "• ○ f(1) = g(2) = h(3) "
              "• ○ f(1) + f(2) = g(3)"),
        ],
        "choices": CH("3", "4", "5", "6", "7"),
        "answer": "④", "topic": "여러 가지 함수", "difficulty": "중",
    },
]

# ───────────────────────── p2: 6~11 ────────────────────────
p2 = [
    {
        "number": 6, "score": 4.2,
        "contents": [
            T("두 집합 "), E(r"A = \{x \mid x^{2} - 4x - 5 \leq 0\}"), T(", "),
            E(r"B = \{x \mid a+3 < x \leq b-2\}"), T("에 대하여 "), E(r"A \subset B"),
            T("를 만족시키는 정수 "), E("a"), T("의 최댓값을 "), E("M"),
            T(", 정수 "), E("b"), T("의 최솟값을 "), E("m"), T("이라 할 때, "),
            E("M+m"), T("의 값은?"),
        ],
        "choices": CH("1", "2", "3", "4", "5"),
        "answer": "②", "topic": "집합 사이의 포함관계", "difficulty": "중",
    },
    {
        "number": 7, "score": 4.4,
        "contents": [
            T("전체집합 "), E("U"), T("의 세 부분집합 "), E("A"), T(", "), E("B"),
            T(", "), E("C"), T("에 대하여 옳은 것만을 <보기>에서 있는 대로 고른 것은?"),
            T(r"<보기> ㄱ. (A \cap B) \cup (A \cap B^{C}) = A "
              r"• ㄴ. (A-B)-C = A-(B \cap C) "
              r"• ㄷ. \{A \cap (A-B)^{C}\} \cup \{(A \cup B) \cap B\} = B"),
        ],
        "choices": CH(("t", "ㄱ"), ("t", "ㄴ"), ("t", "ㄷ"), ("t", "ㄱ, ㄷ"),
                      ("t", "ㄴ, ㄷ")),
        "answer": "④", "topic": "집합의 연산법칙", "difficulty": "중",
    },
    {
        "number": 8, "score": 4.4,
        "contents": [
            T("실수 "), E("x"), T("에 대하여 두 조건 "), E("p"), T("와 "), E("q"),
            T("가 "), E(r"p : |x-1| \leq 5"), T(", "),
            E(r"q : x^{2} - ax - 6a^{2} \leq 0"), T("일 때, 명제 "), E(r"p \to q"),
            T("의 역과 대우가 모두 참일 때 양수 "), E("a"), T("의 값은?"),
        ],
        "choices": CH("1", "2", "3", "4", "5"),
        "answer": "②", "topic": "명제의 역과 대우", "difficulty": "중",
    },
    {
        "number": 9, "score": 4.4,
        "contents": [
            T("전체집합 "), E("U"), T("에서 세 조건 "), E("p"), T(", "), E("q"),
            T(", "), E("r"), T("의 진리집합을 각각 "), E("P"), T(", "), E("Q"),
            T(", "), E("R"), T("이라 하자. "), E("p"), T("는 ~"), E("q"),
            T("이기 위한 충분조건이고, "), E("q"), T("는 ~"), E("r"),
            T("이기 위한 필요조건일 때, 옳지 않은 것은? (단, "), E("P"), T(", "),
            E("Q"), T(", "), E("R"), T("은 모두 공집합이 아니다.)"),
        ],
        "choices": CH(r"P \subset R", r"P \subset Q^{C}", r"R \subset P^{C}",
                      r"Q^{C} \subset R", r"P \subset (R \cap Q^{C})"),
        "answer": "③", "topic": "충분조건과 필요조건", "difficulty": "중",
    },
    {
        "number": 10, "score": 4.6,
        "contents": [
            T("실수 전체의 집합 "), E("R"), T("에 대하여 함수 "), E(r"f : R \to R"),
            T("는"),
            EB(r"f(x) = \begin{cases} \frac{1}{4}x + 1 & (x \geq 0) \\"
               r" 2x + k & (x < 0) \end{cases}"),
            T("이다. 함수 "), E("f"), T("의 역함수 "), E("f^{-1}"),
            T("가 존재할 때, 집합 "),
            E(r"\{x \mid \{f(x)\}^{2} = f(x)f^{-1}(x)\}"),
            T("의 모든 원소의 곱은?"),
        ],
        "choices": CH(r"-\frac{8}{3}", r"-\frac{2}{3}", r"\frac{2}{3}",
                      r"\frac{4}{3}", r"\frac{8}{3}"),
        "answer": "③", "topic": "역함수", "difficulty": "상",
    },
    {
        "number": 11, "score": 4.6,
        "contents": [
            T("두 함수 "), E(r"f(x) = \frac{2x-1}{x+2}"), T(", "),
            E(r"g(x) = \frac{1}{x} + 1"), T("에 대하여 함수 "), E("h(x)"),
            T("가 "), E(r"x \neq -2"), T(", "), E(r"x \neq 0"), T("인 실수 "),
            E("x"), T("에 대하여 "), E(r"(h \circ g)(x) = f(x)"),
            T("를 만족시킬 때, "),
            E(r"((g \circ h^{-1})^{-1} \circ (h^{-1} \circ g^{-1})^{-1})(2)"),
            T("의 값은?"),
        ],
        "choices": CH("-4", "-5", "-6", "-7", "-8"),
        "answer": "⑤", "topic": "합성함수", "difficulty": "상",
    },
]

# ───────────────────────── p3: 12~15 ───────────────────────
p3 = [
    {
        "number": 12, "score": 4.6,
        "contents": [
            T("그림은 이차함수 "), E("y = f(x)"), T("의 그래프이다. 방정식 "),
            E(r"(f \circ f)(x) = 2"), T("의 서로 다른 모든 실근의 합은?"),
            F("이차함수 y=f(x)의 그래프. 아래로 볼록한 포물선으로 x축과 x=1, x=5에서 만나고 "
              "꼭짓점은 (3, -2). 꼭짓점까지 x=3 세로 점선과 y=-2 가로 점선.",
              [0.20, 0.12, 0.78, 0.62]),
        ],
        "choices": CH("4", "6", "10", "12", "16"),
        "answer": "④", "topic": "합성함수", "difficulty": "상",
    },
    {
        "number": 13, "score": 4.6,
        "contents": [
            T("함수 "), E(r"y = \sqrt{2x+4} + 3"),
            T("의 역함수의 그래프와 직선 "), E("y = 2x + k"),
            T("가 서로 다른 두 점에서 만나도록 하는 실수 "), E("k"),
            T("의 최댓값은?"),
        ],
        "choices": CH("-10", "-8", "-6", "-4", "-2"),
        "answer": "②", "topic": "무리함수", "difficulty": "상",
    },
    {
        "number": 14, "score": 4.8,
        "contents": [
            T("함수 "), E(r"f(x) = \sqrt{ax+b} + c"),
            T("의 그래프가 아래 그림과 같다."),
            F("무리함수 y=f(x)의 그래프. 왼쪽 위에서 오른쪽 아래로 내려오는 곡선이 "
              "제1사분면의 한 점에서 끝나며, 그 끝점에서 x축·y축으로 점선을 내림.",
              [0.18, 0.12, 0.85, 0.60]),
            T("이때, 함수 "), E(r"g(x) = -\sqrt{bx+a} - c"),
            T("에 대하여 옳은 것만을 <보기>에서 있는 대로 고른 것은?"),
            T(r"<보기> ㄱ. 정의역은 \left\{ x \mid x \geq -\frac{a}{b} \right\}이다. "
              r"• ㄴ. 치역은 \{y \mid y \leq -c\}이다. "
              r"• ㄷ. 함수 g(x)의 그래프는 오직 하나의 사분면을 지난다. "
              r"• ㄹ. 두 집합 A = \left\{ (x,\ y) \mid y = mx,\ \frac{bc}{a} < m < 0 \right\}, "
              r"B = \{(x,\ y) \mid y = g(x)\}에 대하여 A\cap B = \varnothing이다."),
        ],
        "choices": CH(("t", "ㄱ, ㄴ, ㄷ"), ("t", "ㄱ, ㄴ, ㄹ"), ("t", "ㄱ, ㄷ, ㄹ"),
                      ("t", "ㄴ, ㄷ, ㄹ"), ("t", "ㄱ, ㄴ, ㄷ, ㄹ")),
        "answer": "①", "topic": "무리함수", "difficulty": "상",
    },
    {
        "number": 15, "score": 4.8,
        "contents": [
            T("실수 전체의 집합 "), E("U"), T("의 두 부분집합 "), E("A"), T(", "),
            E("B"), T("에 대하여 "), E("n(A) = 5"), T(", "),
            E(r"B = \left\{ \frac{x+k}{3} \middle| x \in A \right\}"),
            T("이다. 두 집합 "), E("A"), T(", "), E("B"),
            T("가 다음 조건을 모두 만족시킬 때, 상수 "), E("k"), T("의 값은?"),
            T(r"<상자> ○ A\cap B = \{8,\ 11\} "
              r"• ○ 집합 A의 모든 원소의 합은 39이다. "
              r"• ○ 집합 A\cup B의 모든 원소의 합은 53이다."),
        ],
        "choices": CH("12", "13", "14", "20", "24"),
        "answer": "①", "topic": "유한집합의 원소의 개수", "difficulty": "상",
    },
]

# ─────────────────── p4: 16 + 서답형 1·2 ───────────────────
p4 = [
    {
        "number": 16, "score": 4.8,
        "contents": [
            T("양수 "), E("a"), T("에 대하여 이차함수 "), E(r"f(x) = x^{2} - ax"),
            T("의 그래프와 직선 "), E(r"g(x) = \frac{2}{a}x"),
            T("가 두 점 O, A에서 만날 때, 이차함수 "), E("y = f(x)"),
            T("의 그래프의 꼭짓점을 B, 선분 AB의 중점을 C라 하자. 이때, 점 C에서 "),
            E("y"),
            T("축에 내린 수선의 발을 H라 하면 선분 CH의 길이의 최솟값은?"),
            F("이차함수 f(x)=x^2-ax의 그래프와 직선 g(x)=(2/a)x가 원점 O와 점 A에서 만난다. "
              "포물선의 꼭짓점 B, 선분 AB의 중점 C, 점 C에서 y축에 내린 수선의 발 H(직각 표시).",
              [0.10, 0.22, 0.80, 0.78]),
        ],
        "choices": CH(r"\frac{\sqrt{2}}{3}", r"\frac{\sqrt{3}}{2}", "1",
                      r"\sqrt{2}", r"\sqrt{3}"),
        "answer": "⑤", "topic": "절대부등식", "difficulty": "상",
    },
    {
        "number": 17, "score": 6, "label_type": "서답형",
        "contents": [
            T("[서답형 1]"), T(" 전체집합 "), E("U"), T("의 두 부분집합 "), E("A"),
            T(", "), E("B"), T("에 대하여 "), E("n(U) = 50"), T(", "),
            E("n(A) = 22"), T(", "), E(r"n(A - B^{C}) = 5"), T(", "),
            E(r"n(A^{C} \cap B^{C}) = 7"), T("일 때, "), E("n(B)"),
            T("의 값을 구하고 그 과정을 서술하시오."),
        ],
        "choices": [], "sub_questions": [],
        "answer": r"$26$",
        "solution": (
            r"step1) $A - B^{C} = A \cap B$이므로 $n(A \cap B) = 5$이다." "\n"
            r"step2) $A^{C} \cap B^{C} = (A \cup B)^{C}$이므로 "
            r"$n(A \cup B) = n(U) - n((A \cup B)^{C}) = 50 - 7 = 43$이다." "\n"
            r"step3) $n(A \cup B) = n(A) + n(B) - n(A \cap B)$에서 "
            r"$43 = 22 + n(B) - 5$이다." "\n"
            r"step4) 따라서 $n(B) = 26$이다."
        ),
        "topic": "유한집합의 원소의 개수", "difficulty": "하",
    },
    {
        "number": 18, "score": 6, "label_type": "서답형",
        "contents": [
            T("[서답형 2]"), T(" 함수 "), E("f(x) = -x + 2"), T("에 대하여"),
            EB(r"f^{1} = f,\ \ f^{n+1} = f \circ f^{n}\ \ (n은 자연수)"),
            T("으로 정의할 때, "), E("f^{2025}(1) + f^{2026}(2)"),
            T("의 값을 구하고 그 과정을 서술하시오."),
        ],
        "choices": [], "sub_questions": [],
        "answer": r"$3$",
        "solution": (
            r"step1) $f^{2}(x) = f(f(x)) = -(-x+2)+2 = x$이므로 $f^{2}$는 항등함수이다." "\n"
            r"step2) 따라서 자연수 $k$에 대하여 $f^{2k} (x) = x$, $f^{2k+1}(x) = f(x)$이다." "\n"
            r"step3) $2025$는 홀수이므로 $f^{2025}(1) = f(1) = -1+2 = 1$이다." "\n"
            r"step4) $2026$은 짝수이므로 $f^{2026}(2) = 2$이다." "\n"
            r"step5) 따라서 $f^{2025}(1) + f^{2026}(2) = 1 + 2 = 3$이다."
        ),
        "topic": "합성함수", "difficulty": "중",
    },
]

# ─────────────────── p5: 서답형 3·4 ────────────────────────
p5 = [
    {
        "number": 19, "score": 8, "label_type": "서답형",
        "contents": [
            T("[서답형 3]"), T(" 실수 "), E("x"), T("에 대하여 두 조건 "), E("p"),
            T(", "), E("q"), T("가"),
            EB(r"p : ax^{2} - 6x - 5 \geq 0,\ \ q : x^{2} - 4bx + 64 \geq 0"),
            T("이다. 다음 두 명제 (가), (나)가 모두 참이 되도록 하는 정수 "), E("a"),
            T("의 최댓값을 "), E("M"), T(", 자연수 "), E("b"), T("의 최댓값을 "),
            E("N"), T("이라 할 때, "), E("M+N"),
            T("의 값을 구하고 그 과정을 서술하시오."),
            T("<상자> (가) 모든 실수 x에 대하여 ~p이다. "
              "• (나) p는 ~q이기 위한 필요조건이다."),
        ],
        "choices": [], "sub_questions": [],
        "answer": r"$2$",
        "solution": (
            r"step1) 조건 (가)에서 조건 $p$의 진리집합은 공집합이므로 "
            r"모든 실수 $x$에 대하여 $ax^{2} - 6x - 5 < 0$이다." "\n"
            r"step2) 따라서 $a < 0$이고 판별식 $D_{1} = 36 + 20a < 0$이어야 하므로 "
            r"$a < -\frac{9}{5}$이고, 정수 $a$의 최댓값은 $M = -2$이다." "\n"
            r"step3) 조건 (나)에서 $p$가 ~$q$이기 위한 필요조건이므로 "
            r"~$q$의 진리집합은 조건 $p$의 진리집합인 공집합에 포함된다." "\n"
            r"step4) 즉 ~$q$의 진리집합이 공집합이어야 하므로 모든 실수 $x$에 대하여 "
            r"$x^{2} - 4bx + 64 \geq 0$이고, 판별식 "
            r"$\frac{D_{2}}{4} = 4b^{2} - 64 \leq 0$에서 $-4 \leq b \leq 4$이다." "\n"
            r"step5) 따라서 자연수 $b$의 최댓값은 $N = 4$이고, $M + N = -2 + 4 = 2$이다."
        ),
        "topic": "충분조건과 필요조건", "difficulty": "상",
    },
    {
        "number": 20, "score": 10, "label_type": "서답형",
        "contents": [
            T("[서답형 4]"), T(" 함수 "), E(r"y = \sqrt{3x}\ (0 < x < 27)"),
            T("의 그래프 위를 움직이는 점 A에 대하여 점 A와 원점 O, 점 "),
            E("B(27,\\ 9)"), T("를 꼭짓점으로 하는 삼각형 OAB의 넓이의 최댓값은 "),
            E(r"\frac{3^{m}}{2^{n}}"), T("이다. 자연수 "), E("m"), T(", "), E("n"),
            T("의 값을 구하고 그 과정을 서술하시오."),
        ],
        "choices": [], "sub_questions": [],
        "answer": r"$m=5$, $n=3$",
        "solution": (
            r"step1) 점 A의 좌표를 $(t,\ \sqrt{3t})\ (0 < t < 27)$라 하면 "
            r"$s = \sqrt{3t}$로 놓을 때 $0 < s < 9$이고 $t = \frac{s^{2}}{3}$이다." "\n"
            r"step2) 점 $\mathrm{B}(27,\ 9)$도 곡선 위의 점이고, 삼각형 OAB의 넓이는 "
            r"$S = \frac{1}{2}|x_{A} y_{B} - x_{B} y_{A}| "
            r"= \frac{1}{2}\left| 9t - 27\sqrt{3t} \right|$이다." "\n"
            r"step3) $t = \frac{s^{2}}{3}$을 대입하면 "
            r"$S = \frac{1}{2}|3s^{2} - 27s| = \frac{3}{2}(9s - s^{2})$이다." "\n"
            r"step4) $9s - s^{2} = -\left(s - \frac{9}{2}\right)^{2} + \frac{81}{4}$이므로 "
            r"$s = \frac{9}{2}$일 때 최대이고, 이때 "
            r"$S = \frac{3}{2} \times \frac{81}{4} = \frac{243}{8}$이다." "\n"
            r"step5) $\frac{243}{8} = \frac{3^{5}}{2^{3}}$이므로 $m = 5$, $n = 3$이다."
        ),
        "topic": "무리함수", "difficulty": "상",
    },
]

for i, qs in enumerate((p1, p2, p3, p4, p5), 1):
    fp = os.path.join(OUT, f"p{i}_merged.json")
    with open(fp, "w", encoding="utf-8") as f:
        json.dump({"header": "", "questions": qs}, f, ensure_ascii=False, indent=1)
    print("WROTE", fp, len(qs), "문항, 배점합",
          round(sum(q["score"] for q in qs), 1))
