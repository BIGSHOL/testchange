# -*- coding: utf-8 -*-
"""정답·해설 기입 — 세션 풀이(API 0원). build_ocr.py 산출 JSON 에 answer/solution 추가."""
import json
import math
from pathlib import Path

OCR = Path(__file__).resolve().parents[1] / "ocr"

MC = {1: "③", 2: "⑤", 3: "②", 4: "①", 5: "③", 6: "①", 7: "②", 8: "①", 9: "④",
      10: "⑤", 11: "③", 12: "④", 13: "③", 14: "⑤", 15: "④", 16: "④", 17: "①", 18: "②"}

ESSAY = {
    19: ("$y=\\frac{1}{3}x^{2}-\\frac{8}{3}x+\\frac{7}{3}$", [
        "step1) 두 점 $(1, 0)$, $(7, 0)$의 중점의 $x$좌표는 $4$이므로 축은 $x=4$이다.",
        "step2) 꼭짓점이 직선 $y=-3$ 위에 있으므로 꼭짓점은 $(4, -3)$이다.",
        "step3) $y=a(x-4)^{2}-3$으로 놓고 점 $(1, 0)$을 대입한다.",
        "step4) $0=9a-3$이므로 $a=\\frac{1}{3}$이다.",
        "step5) $y=\\frac{1}{3}(x-4)^{2}-3$을 전개한다.",
        "step6) 따라서 $y=\\frac{1}{3}x^{2}-\\frac{8}{3}x+\\frac{7}{3}$이다.",
    ]),
    21: ("$\\frac{7\\sqrt{3}}{2}\\,\\mathrm{cm}^{2}$", [
        "step1) 대각선 $\\overline{\\mathrm{AC}}$를 그어 두 삼각형으로 나눈다.",
        "step2) $\\triangle \\mathrm{ABC}=\\frac{1}{2}\\times 3\\times 4\\times \\sin 60^{\\circ}$",
        "step3) $=\\frac{1}{2}\\times 3\\times 4\\times \\frac{\\sqrt{3}}{2}=3\\sqrt{3}\\,(\\mathrm{cm}^{2})$이다.",
        "step4) $\\triangle \\mathrm{ACD}=\\frac{1}{2}\\times \\sqrt{3}\\times 2\\times \\sin(180^{\\circ}-150^{\\circ})$",
        "step5) $=\\frac{1}{2}\\times \\sqrt{3}\\times 2\\times \\frac{1}{2}=\\frac{\\sqrt{3}}{2}\\,(\\mathrm{cm}^{2})$이다.",
        "step6) 따라서 $\\square \\mathrm{ABCD}=3\\sqrt{3}+\\frac{\\sqrt{3}}{2}=\\frac{7\\sqrt{3}}{2}\\,(\\mathrm{cm}^{2})$이다.",
    ]),
    22: ("$\\sin x^{\\circ}=\\frac{9\\sqrt{10}}{50}$", [
        "step1) $\\overline{\\mathrm{AM}}=\\overline{\\mathrm{MD}}=3$, $\\overline{\\mathrm{DN}}=\\overline{\\mathrm{NC}}=2$이다.",
        "step2) $\\overline{\\mathrm{BM}}=\\sqrt{3^{2}+4^{2}}=5$이다.",
        "step3) $\\overline{\\mathrm{BN}}=\\sqrt{6^{2}+2^{2}}=2\\sqrt{10}$이다.",
        "step4) $\\triangle \\mathrm{ABM}=6$, $\\triangle \\mathrm{MDN}=3$, $\\triangle \\mathrm{BCN}=6$이다.",
        "step5) $\\triangle \\mathrm{MBN}=24-(6+3+6)=9$이다.",
        "step6) $\\triangle \\mathrm{MBN}=\\frac{1}{2}\\times 5\\times 2\\sqrt{10}\\times \\sin x^{\\circ}$이므로",
        "step7) $5\\sqrt{10}\\sin x^{\\circ}=9$이다.",
        "step8) 따라서 $\\sin x^{\\circ}=\\frac{9}{5\\sqrt{10}}=\\frac{9\\sqrt{10}}{50}$이다.",
    ]),
}

SUB20 = {
    1: ("$\\angle \\mathrm{A}=30^{\\circ}$", [
        "step1) $4x^{2}+4x-3=0$에서 $(2x-1)(2x+3)=0$이다.",
        "step2) $x=\\frac{1}{2}$ 또는 $x=-\\frac{3}{2}$이므로 큰 근은 $\\frac{1}{2}$이다.",
        "step3) $\\sin A=\\frac{1}{2}$이고 $0^{\\circ}<\\angle \\mathrm{A}<90^{\\circ}$이다.",
        "step4) 따라서 $\\angle \\mathrm{A}=30^{\\circ}$이다.",
    ]),
    2: ("$\\sqrt{3}$", [
        "step1) $\\angle \\mathrm{A}=30^{\\circ}$이므로 $\\cos A=\\frac{\\sqrt{3}}{2}$, $\\sin A=\\frac{1}{2}$이다.",
        "step2) $\\cos 60^{\\circ}+\\cos A=\\frac{1}{2}+\\frac{\\sqrt{3}}{2}>0$이다.",
        "step3) $\\sin A-\\sin 60^{\\circ}=\\frac{1}{2}-\\frac{\\sqrt{3}}{2}<0$이다.",
        "step4) (주어진 식)$=\\left(\\frac{1}{2}+\\frac{\\sqrt{3}}{2}\\right)-\\left(\\frac{1}{2}-\\frac{\\sqrt{3}}{2}\\right)$",
        "step5) 따라서 (주어진 식)$=\\sqrt{3}$이다.",
    ]),
}

# 수치 검산
assert abs((4 - 1) ** 2 / 3 - 3) < 1e-12                           # a=1/3 → f(1)=0
assert abs(0.5 * 3 * 4 * math.sin(math.radians(60)) + 0.5 * math.sqrt(3) * 2 * 0.5
           - 7 * math.sqrt(3) / 2) < 1e-12
bm, bn = 5, 2 * math.sqrt(10)
ang = math.degrees(math.atan2(4, 3) - math.atan2(2, 6))
assert abs(math.sin(math.radians(ang)) - 9 * math.sqrt(10) / 50) < 1e-12
assert abs(4 * 0.25 + 2 - 3) < 1e-12                               # 1/2 is a root
c = math.cos(math.radians(60)) + math.cos(math.radians(30))
s = math.sin(math.radians(30)) - math.sin(math.radians(60))
assert abs(math.sqrt(c * c) + math.sqrt(s * s) - math.sqrt(3)) < 1e-12

for n in range(1, 5):
    f = OCR / f"p{n}_merged.json"
    d = json.loads(f.read_text(encoding="utf-8"))
    for q in d["questions"]:
        num = q["number"]
        if num in MC:
            q["answer"] = MC[num]
            q.pop("solution", None)
        elif num in ESSAY:
            q["answer"], lines = ESSAY[num]
            q["solution"] = "\n".join(lines)
        elif num == 20:
            q.pop("answer", None)
            q.pop("solution", None)
            for sq in q["sub_questions"]:
                sq["answer"], lines = SUB20[sq["number"]]
                sq["solution"] = "\n".join(lines)
    f.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
print("ok")
