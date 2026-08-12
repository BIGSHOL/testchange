# -*- coding: utf-8 -*-
import json, io, os

def T(v): return {"type": "text", "value": v}
def E(v): return {"type": "equation", "value": v}
def ch(*vals, kind="equation"):
    return [{"number": i + 1, "contents": [{"type": kind, "value": v}]} for i, v in enumerate(vals)]
def cht(*vals):
    return [{"number": i + 1, "contents": [{"type": "text", "value": v}]} for i, v in enumerate(vals)]

questions = []

questions.append({
    "number": 1, "score": 2.8, "type": "객관식", "label": None,
    "contents": [T("두 점 \\mathrm{A}(3,~-5), \\mathrm{B}(-3,~-4)에 대하여 선분 \\mathrm{AB}를 2:3으로 내분하는 점을 (a,~b)라 할 때, a+b의 값은?")],
    "choices": ch("-4", "-3", "-2", "-1", "1"),
})

questions.append({
    "number": 2, "score": 2.8, "type": "객관식", "label": None,
    "contents": [T("직선 2x-y+3=0을 x축의 방향으로 1만큼, y축의 방향으로 -2만큼 평행이동한 후, 직선 y=x에 대하여 대칭이동한 도형의 방정식은 x+ay+b=0이다. a+2b의 값은?")],
    "choices": ch("-2", "-1", "0", "1", "2"),
})

questions.append({
    "number": 3, "score": 3.0, "type": "객관식", "label": None,
    "contents": [T("세 점 \\mathrm{O}(0,~0), \\mathrm{A}(3,~1), \\mathrm{B}(4,~0)을 지나는 원의 넓이는?")],
    "choices": ch("4\\pi", "5\\pi", "6\\pi", "7\\pi", "8\\pi"),
})

questions.append({
    "number": 4, "score": 3.0, "type": "객관식", "label": None,
    "contents": [T("두 점 \\mathrm{A}(3,~-3), \\mathrm{B}(5,~4)에서 같은 거리에 있는 직선 y=x+1 위의 점의 좌표를 (a,~b)라 할 때, a+b의 값은?")],
    "choices": ch("1", "\\frac{3}{2}", "2", "\\frac{5}{2}", "3"),
})

questions.append({
    "number": 5, "score": 3.2, "type": "객관식", "label": None,
    "contents": [T("전체집합 U=\\{x \\mid x는 50 이하의 자연수\\}의 두 부분집합 A, B에 대하여 집합 A=\\{x \\mid x는 9의 배수\\}, 집합 B=\\{x \\mid x는 18의 약수\\}일 때, 다음 중 옳은 것은?")],
    "choices": ch("\\{45\\} \\in A", "3 \\notin A^{c}", "n(B)=7", "n(B-A^{c})=2", "n(A^{c}-A)=0"),
})

questions.append({
    "number": 6, "score": 3.2, "type": "객관식", "label": None,
    "contents": [T("두 점 \\mathrm{A}(7,~4), \\mathrm{B}(2,~1)과 x축 위의 한 점 \\mathrm{P}, 직선 y=x 위의 한 점 \\mathrm{Q}에 대하여 \\overline{\\mathrm{AP}}+\\overline{\\mathrm{PQ}}+\\overline{\\mathrm{QB}}의 최솟값은?")],
    "choices": ch("6\\sqrt{2}", "2\\sqrt{19}", "4\\sqrt{5}", "2\\sqrt{21}", "2\\sqrt{22}"),
})

questions.append({
    "number": 7, "score": 3.2, "type": "객관식", "label": None,
    "contents": [T("어느 학급 학생 30명을 대상으로 수학학원과 영어학원을 다니는 학생 수를 조사하였더니, 수학학원을 다니는 학생이 20명, 영어학원을 다니는 학생이 14명이었다. 어느 학원도 다니지 않는 학생이 7명일 때, 수학학원만 다니는 학생의 수는?")],
    "choices": ch("8", "9", "10", "11", "12"),
})

questions.append({
    "number": 8, "score": 3.4, "type": "객관식", "label": None,
    "contents": [T("두 직선 x-y+3=0, kx+y-2k+3=0이 제 2사분면에서 만나도록 하는 모든 정수 k의 값의 합은?")],
    "choices": ch("-6", "-3", "0", "3", "6"),
})

questions.append({
    "number": 9, "score": 3.4, "type": "객관식", "label": None,
    "contents": [T("전체집합 U의 두 부분집합 A, B에 대하여 (A^{c} \\cap B)^{c}=\\{1,~2,~3,~5,~7\\}, B=\\{1,~3,~6,~8\\}일 때, 집합 A의 모든 원소의 합의 최댓값을 m, 최솟값을 n이라 할 때, m+n의 값은?")],
    "choices": ch("18", "20", "22", "24", "26"),
})

questions.append({
    "number": 10, "score": 3.6, "type": "객관식", "label": None,
    "contents": [T("점 (3,~4)에서 원 x^{2}+y^{2}=4에 그은 접선 중 x절편이 양수인 접선의 기울기는 \\frac{a+b\\sqrt{21}}{5} 이다. a+b의 값은? (단, a, b는 정수이다.)")],
    "choices": ch("6", "8", "10", "12", "14"),
})

questions.append({
    "number": 11, "score": 3.8, "type": "객관식", "label": None,
    "contents": [T("이차함수 y=x^{2}+3x의 그래프 위의 점과 직선 2x-y-5=0 사이의 거리의 최솟값이 \\frac{q}{p}\\sqrt{5} 일 때, p+q의 값은? (단, p, q는 서로소인 자연수)")],
    "choices": ch("35", "36", "37", "38", "39"),
})

questions.append({
    "number": 12, "score": 3.8, "type": "객관식", "label": None,
    "contents": [
        T("세 양수 a, b, r에 대하여 두 원"),
        E("C_{1} : x^{2}+y^{2}=r^{2}"),
        E("C_{2} : (x+a)^{2}+(y-b)^{2}=r^{2}"),
        T("이 다음 조건을 만족시킬 때, a+b-r의 값은?"),
        T("<상자> (가) 원 C_{2}는 원 C_{1}의 중심을 지난다. • (나) 두 원 C_{1}, C_{2}는 모두 직선 3x+4y+5=0에 접한다."),
    ],
    "choices": ch("\\frac{1}{5}", "\\frac{2}{5}", "\\frac{3}{5}", "\\frac{4}{5}", "1"),
})

questions.append({
    "number": 13, "score": 4.0, "type": "객관식", "label": None,
    "contents": [T("서로 다른 부호를 갖는 0이 아닌 정수 p, q에 대하여 원 x^{2}+y^{2}=10을 x축의 방향으로 p만큼, y축의 방향으로 q만큼 평행이동한 원이 직선 y=3x-5와 접하도록 하는 모든 순서쌍 (p,~q)의 개수는?")],
    "choices": ch("3", "4", "5", "6", "7"),
})

questions.append({
    "number": 14, "score": 4.2, "type": "객관식", "label": None,
    "contents": [T("원 x^{2}+y^{2}=16 위를 움직이는 두 점 \\mathrm{A}(4,~0), \\mathrm{B}(-3,~-\\sqrt{7})과 원 위를 움직이는 점 \\mathrm{A}, \\mathrm{B}가 아닌 점 \\mathrm{C}가 있다. 삼각형 \\mathrm{ABC}의 넓이의 최댓값이 a\\sqrt{7}+b\\sqrt{14} 일 때, a+b의 값은? (단, a, b는 유리수이다.)")],
    "choices": ch("3", "4", "5", "6", "7"),
})

questions.append({
    "number": 15, "score": 4.2, "type": "객관식", "label": None,
    "contents": [T("점 (1,~2)를 지나는 직선 중에서 원점과의 거리가 최대인 직선을 l_{1}이라 하고, 직선 l_{1}이 x축과 만나는 점을 \\mathrm{A}라 하자. 직선 l_{1} 위의 제2사분면 위의 한 점 \\mathrm{P}(a,~b)에서 수직으로 만나는 직선 l_{2}에 대하여 l_{2}가 x축과 만나는 점을 \\mathrm{B}라 하자. 삼각형 \\mathrm{ABP}의 넓이가 20일 때, a+b의 값은?")],
    "choices": ch("1", "3", "5", "7", "9"),
})

questions.append({
    "number": 16, "score": 4.4, "type": "객관식", "label": None,
    "contents": [
        T("전체집합 U=\\{1,~2,~4,~8,~16\\}의 두 부분집합 A, B가 다음 조건을 만족시킬 때, 모든 순서쌍 (A,~B)의 개수는?"),
        T("<상자> (가) A \\cup B=U • (나) x \\in A이면 \\frac{16}{x} \\in A이다. • (다) A \\neq \\varnothing, B \\neq \\varnothing"),
    ],
    "choices": ch("72", "73", "74", "75", "76"),
})

questions.append({
    "number": 17, "score": 4.4, "type": "객관식", "label": None,
    "contents": [T("좌표평면 위의 네 점 \\mathrm{O}(0,~0), \\mathrm{A}(-2,~3), \\mathrm{B}(2,~6), \\mathrm{C}(6,~0)을 꼭짓점으로 하는 사다리꼴 \\mathrm{OABC}에서 선분 \\mathrm{OA}를 1:3으로 내분하는 점을 지나는 직선 y=mx+n이 사다리꼴 \\mathrm{OABC}의 넓이 S를 이등분한다. 이때 \\frac{8}{9} \\times S \\times (n-m)의 값은? (단, S, m, n은 상수)")],
    "choices": ch("9", "10", "12", "14", "15"),
})

questions.append({
    "number": 18, "score": 4.6, "type": "객관식", "label": None,
    "contents": [
        T("좌표평면 위의 점 \\mathrm{P}(x,~y)가 다음과 같은 규칙에 따라 이동한다."),
        T("<상자> [규칙] • (가) y \\geq 2x이면 직선 y=x에 대하여 대칭이동한다. • (나) y < 2x이면 x축의 방향으로 -1만큼, y축의 방향으로 2만큼 평행이동한다."),
        T("자연수 a, n에 대하여 점 \\mathrm{P}가 점 (a,~a)에서 출발하여 위의 규칙을 따라 n번 이동한 후의 점을 \\mathrm{P}_{n}이라 하자. 점 \\mathrm{P}_{3}과 점 \\mathrm{P}_{8}을 각각 중심으로 하는 원이 모두 x축과 y축에 동시에 접하고 서로 다른 두 점 \\mathrm{A}, \\mathrm{B}에서 만날 때, 선분 \\mathrm{AB}의 길이는?"),
    ],
    "choices": ch("2\\sqrt{13}", "2\\sqrt{15}", "2\\sqrt{17}", "2\\sqrt{19}", "2\\sqrt{21}"),
})

questions.append({
    "number": 19, "score": 6, "type": "서술형", "label": "[서술형 1]",
    "contents": [T("[서술형 1] 원 x^{2}+y^{2}+6x-2y+7=0의 __중심__과 __반지름의 길이__를 구하시오.")],
})

questions.append({
    "number": 20, "score": 7, "type": "서술형", "label": "[서술형 2]",
    "contents": [T("[서술형 2] 두 점 \\mathrm{A}(-1,~-3), \\mathrm{B}(5,~-5)를 이은 선분 \\mathrm{AB}의 수직이등분선의 방정식을 구하시오.")],
})

questions.append({
    "number": 21, "score": 10, "type": "서술형", "label": "[서술형 3]",
    "contents": [T("[서술형 3] 점 \\mathrm{P}(2,~-3)을 원점에 대하여 대칭이동한 점을 \\mathrm{Q}, 점 \\mathrm{P}를 직선 y=x에 대하여 대칭이동한 점을 \\mathrm{R}이라 할 때, 삼각형 \\mathrm{PQR}의 넓이를 구하시오.")],
})

questions.append({
    "number": 22, "score": 12, "type": "서술형", "label": "[서술형 4]",
    "contents": [T("[서술형 4] 두 집합 A=\\{4,~a^{2}+1,~2a^{2}-6\\}, B=\\{2,~4,~a-1\\}에 대하여 (A-B) \\cup (B-A)=\\{1,~5\\}일 때, 상수 __a값__과 __집합 A, B__를 구하시오.")],
})

doc = {
    "meta": {"exam_id": 4333, "ocr_source": "session-vision"},
    "header": {"title": "2025학년도 1학년 2학기 중간고사 공통수학2 (대원고등학교)"},
    "questions": questions,
}

out = r"D:\시험지 한글화\db\ocr_pilot\4333.json"
os.makedirs(os.path.dirname(out), exist_ok=True)
with io.open(out, "w", encoding="utf-8") as f:
    json.dump(doc, f, ensure_ascii=False, indent=1)

ans = {"exam_id": 4333, "answer_pages": [], "items": []}
with io.open(r"D:\시험지 한글화\db\ocr_pilot\4333.answers.json", "w", encoding="utf-8") as f:
    json.dump(ans, f, ensure_ascii=False, indent=1)

# checksum
tot = sum(q["score"] for q in questions)
print("questions:", len(questions), "score total:", round(tot, 2))
print("obj:", sum(1 for q in questions if q["type"] == "객관식"), "essay:", sum(1 for q in questions if q["type"] == "서술형"))
