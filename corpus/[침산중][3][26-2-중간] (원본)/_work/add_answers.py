# -*- coding: utf-8 -*-
"""침산중3 26-2-중간 — 정답·해설 기입(세션 풀이, API 0원)."""
import glob, json, math, os
D = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MC = {1: "⑤", 2: "①", 3: "②", 4: "④", 5: "①", 6: "④", 7: "④", 8: "②",
      9: "①", 10: "③", 11: "③", 12: "②", 13: "③", 14: "①", 15: "②", 16: "④"}

ESSAY = {
    17: ("$y=-\\frac{2}{3}x^{2}+\\frac{8}{3}x+\\frac{10}{3}$", [
        "꼭짓점의 좌표가 $(2, 6)$이므로 $y=a(x-2)^{2}+6$이다.",
        "그래프가 점 $(5, 0)$을 지나므로 $9a+6=0$이다.",
        "따라서 $a=-\\frac{2}{3}$이다.",
        "$y=-\\frac{2}{3}(x-2)^{2}+6$을 전개한다.",
        "$y=-\\frac{2}{3}x^{2}+\\frac{8}{3}x+\\frac{10}{3}$이다.",
    ]),
    18: ("$a=\\frac{3}{2}, b=\\frac{15}{2}$", [
        "$y=a(x-1)^{2}-a+b$이므로 꼭짓점은 $(1, b-a)$이다.",
        "꼭짓점이 $y=-2x+8$ 위에 있으므로 $b-a=6$이다.",
        "점 $(-1, 12)$를 지나므로 $a+2a+b=12$, 즉 $3a+b=12$이다.",
        "두 식을 빼면 $4a=6$이므로 $a=\\frac{3}{2}$이다.",
        "$b=a+6=\\frac{15}{2}$이다.",
    ]),
    19: ("$75\\sqrt{3}-75$", [
        "$\\triangle DBC$에서 $\\overline{BC}=10\\tan 60^{\\circ}=10\\sqrt{3}$이다.",
        "$\\angle DBC=30^{\\circ}$이다.",
        "점 $E$에서 $\\overline{BC}$에 내린 수선의 발을 $H$, $\\overline{EH}=h$라 하자.",
        "$\\triangle EBH$에서 $\\overline{BH}=\\frac{h}{\\tan 30^{\\circ}}=\\sqrt{3}h$이다.",
        "$\\triangle EHC$에서 $\\angle ECH=45^{\\circ}$이므로 $\\overline{HC}=h$이다.",
        "$\\sqrt{3}h+h=10\\sqrt{3}$이므로 $h=\\frac{10\\sqrt{3}}{\\sqrt{3}+1}$이다.",
        "분모를 유리화하면 $h=15-5\\sqrt{3}$이다.",
        "$\\triangle EBC=\\frac{1}{2}\\times 10\\sqrt{3}\\times (15-5\\sqrt{3})$",
        "따라서 넓이는 $75\\sqrt{3}-75$이다.",
    ]),
    20: ("$50+50\\sqrt{2}-50\\sqrt{3}\\,\\mathrm{m}$", [
        "$\\angle ABC=180^{\\circ}-75^{\\circ}=105^{\\circ}$이다.",
        "$\\angle C=180^{\\circ}-30^{\\circ}-105^{\\circ}=45^{\\circ}$이다.",
        "점 $B$에서 $\\overline{AC}$에 내린 수선의 발을 $H$라 하자.",
        "$\\overline{BH}=100\\sin 30^{\\circ}=50$이다.",
        "$\\overline{AH}=100\\cos 30^{\\circ}=50\\sqrt{3}$이다.",
        "$\\angle C=45^{\\circ}$이므로 $\\overline{HC}=\\overline{BH}=50$이다.",
        "$\\overline{BC}=\\frac{50}{\\sin 45^{\\circ}}=50\\sqrt{2}$이다.",
        "돌아간 길은 $100+50\\sqrt{2}$, 원래 길은 $50\\sqrt{3}+50$이다.",
        "따라서 $50+50\\sqrt{2}-50\\sqrt{3}\\,\\mathrm{m}$ 더 갔다.",
    ]),
}

# ── 수치 검산 ─────────────────────────────────────────────────────────
r3, r2 = math.sqrt(3), math.sqrt(2)
f = lambda x: -2 / 3 * x * x + 8 / 3 * x + 10 / 3
assert abs(f(2) - 6) < 1e-12 and abs(f(5)) < 1e-12
a, b = 1.5, 7.5
assert abs(a * 1 + 2 * a + b - 12) < 1e-12 and abs((b - a) - (-2 * 1 + 8)) < 1e-12
B, C, Dp = (0, 0), (10 * r3, 0), (10 * r3, 10)
x = 10 * r3 / (1 + 1 / r3)          # BD: y=x/√3, AC: y=10√3-x
h = x / r3
assert abs(0.5 * 10 * r3 * h - (75 * r3 - 75)) < 1e-9
Bp = (100 * r3 / 2, 50)
Cx = Bp[0] + 50
detour = 100 + math.hypot(Cx - Bp[0], Bp[1])
assert abs(detour - Cx - (50 + 50 * r2 - 50 * r3)) < 1e-9
print("검산 OK", round(75 * r3 - 75, 4), round(50 + 50 * r2 - 50 * r3, 4))

for fp in sorted(glob.glob(os.path.join(glob.escape(D), "ocr", "p*_merged.json"))):
    d = json.load(open(fp, encoding="utf-8"))
    for q in d["questions"]:
        n = q["number"]
        if n in MC:
            q["answer"] = MC[n]
            q.pop("solution", None)
        elif n in ESSAY:
            ans, steps = ESSAY[n]
            q["answer"] = ans
            q["solution"] = "\n".join(f"step{i}) {s}" for i, s in enumerate(steps, 1))
    with open(fp, "w", encoding="utf-8") as fo:
        json.dump(d, fo, ensure_ascii=False, indent=1)
    json.load(open(fp, encoding="utf-8"))
print("written")
