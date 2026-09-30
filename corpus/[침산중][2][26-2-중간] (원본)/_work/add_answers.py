# -*- coding: utf-8 -*-
import json, os
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MC = {1: "①", 2: "④", 3: "①", 4: "③", 5: "④", 6: "④", 7: "④", 8: "⑤",
      9: "②", 10: "②", 11: "③", 12: "①", 13: "③", 14: "⑤", 15: "⑤", 16: "③"}
ESSAY = {
    17: ("$12$", [
        "step1) $2x+y-8=0$에서 $y=-2x+8$이고, $x-y+2=0$에서 $y=x+2$이다.",
        "step2) $-2x+8=x+2$에서 $x=2$, $y=4$이다.",
        "step3) 따라서 두 직선의 교점의 좌표는 $(2,\\ 4)$이다.",
        "step4) $y=0$일 때 $2x-8=0$에서 $x=4$이므로 $(4,\\ 0)$이다.",
        "step5) $y=0$일 때 $x+2=0$에서 $x=-2$이므로 $(-2,\\ 0)$이다.",
        "step6) 밑변의 길이는 $4-(-2)=6$, 높이는 $4$이다.",
        "step7) 넓이는 $\\frac{1}{2}\\times 6\\times 4=12$이다.",
    ]),
    18: ("$3\\,\\mathrm{cm}$", [
        "step1) $\\overline{AB}=\\overline{AC}$이므로 $\\angle ABC=\\angle C=\\frac{180^{\\circ}-36^{\\circ}}{2}=72^{\\circ}$이다.",
        "step2) $\\overline{BD}$는 $\\angle B$의 이등분선이므로 $\\angle ABD=\\angle DBC=36^{\\circ}$이다.",
        "step3) $\\angle BCD=72^{\\circ}$이다.",
        "step4) $\\triangle BCD$에서 $\\angle BDC=180^{\\circ}-36^{\\circ}-72^{\\circ}=72^{\\circ}$이다.",
        "step5) $\\angle A=\\angle ABD=36^{\\circ}$이므로 $\\triangle ABD$는 이등변삼각형이다.",
        "step6) 따라서 $\\overline{AD}=\\overline{BD}$이다.",
        "step7) $\\angle BDC=\\angle BCD=72^{\\circ}$이므로 $\\triangle BCD$도 이등변삼각형이다.",
        "step8) 따라서 $\\overline{BD}=\\overline{BC}=5\\,\\mathrm{cm}$이다.",
        "step9) 두 밑각의 크기가 같은 삼각형은 이등변삼각형이다(성질).",
        "step10) $\\overline{AD}=\\overline{BD}=5\\,\\mathrm{cm}$이다.",
        "step11) $\\overline{DC}=\\overline{AC}-\\overline{AD}=8-5=3\\,(\\mathrm{cm})$이다.",
    ]),
    19: ("$11\\,\\mathrm{cm}$", [
        "step1) $\\triangle ABD$와 $\\triangle CAE$에서",
        "step2) $\\overline{AB}=\\overline{CA}$이다. (빗변)",
        "step3) $\\angle ADB=\\angle CEA=90^{\\circ}$이다.",
        "step4) $\\angle BAD+\\angle CAE=90^{\\circ}$이고,",
        "step5) $\\angle ACE+\\angle CAE=90^{\\circ}$이므로 $\\angle BAD=\\angle ACE$이다.",
        "step6) 따라서 $\\triangle ABD\\equiv\\triangle CAE$ (RHA 합동)이다.",
        "step7) $\\overline{AD}=\\overline{CE}=9\\,\\mathrm{cm}$이다.",
        "step8) $\\overline{AE}=\\overline{BD}=20\\,\\mathrm{cm}$이다.",
        "step9) $\\overline{DE}=\\overline{AE}-\\overline{AD}=20-9=11\\,(\\mathrm{cm})$이다.",
    ]),
    20: ("$\\frac{253}{4}\\pi$", [
        "step1) 직각삼각형의 외심은 빗변의 중점이다.",
        "step2) 따라서 $R=\\frac{1}{2}\\overline{BC}=\\frac{17}{2}$이다.",
        "step3) 외접원의 넓이는 $\\pi\\times\\left(\\frac{17}{2}\\right)^{2}=\\frac{289}{4}\\pi$이다.",
        "step4) $\\triangle ABC$의 넓이는 $\\frac{1}{2}\\times 15\\times 8=60$이다.",
        "step5) 내심을 I라 하면 $\\triangle ABC=\\frac{1}{2}r(15+17+8)=20r$이다.",
        "step6) $20r=60$에서 $r=3$이다.",
        "step7) 내접원의 넓이는 $\\pi\\times 3^{2}=9\\pi$이다.",
        "step8) 넓이의 차는 $\\frac{289}{4}\\pi-9\\pi=\\frac{289}{4}\\pi-\\frac{36}{4}\\pi$이다.",
        "step9) 따라서 구하는 값은 $\\frac{253}{4}\\pi$이다.",
    ]),
}
for n in range(1, 5):
    fp = os.path.join(HERE, "ocr", f"p{n}_merged.json")
    d = json.load(open(fp, encoding="utf-8"))
    for q in d["questions"]:
        if q["number"] in MC:
            q["answer"] = MC[q["number"]]
            q.pop("solution", None)
        else:
            a, sol = ESSAY[q["number"]]
            q["answer"] = a
            q["solution"] = "\n".join(sol)
    json.dump(d, open(fp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("done")
