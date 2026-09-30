# -*- coding: utf-8 -*-
"""정답(객관식)·정답+해설(서답형) 기입 — 세션 풀이(API 0원)."""
import json
import math
from pathlib import Path

OCR = Path(__file__).resolve().parents[1] / "ocr"

MC = {1: "③", 2: "④", 3: "②", 4: "⑤", 5: "⑤", 6: "②", 7: "①", 8: "④",
      9: "①", 10: "②", 11: "③", 12: "⑤", 13: "②", 14: "③", 15: "④", 16: "④"}

# 수치 검산
s = math.sqrt(80)
assert abs(25 * math.pi - 4 * math.pi - 21 * math.pi) < 1e-9          # s1
assert abs(0.5 * (3 * s / 8) * (s / 2) - 7.5) < 1e-9                  # s2
assert 10 + 5 + 10 + 5 == 30                                          # s3
assert (54 / 2) - (180 - 2 * 72) / 2 == 9                             # s4
assert 7 - 3 == 4                                                     # s5

ESSAY = {
    17: ("$21\\pi\\,\\mathrm{cm}^2$", [
        "step1) $\\angle C=90^\\circ$이므로 빗변 $\\overline{AB}$가 외접원의 지름이다.",
        "step2) 외접원의 반지름은 $5\\,\\mathrm{cm}$, 넓이는 $25\\pi\\,\\mathrm{cm}^2$이다.",
        "step3) 내접원의 반지름을 $r$라 하면 $\\triangle ABC$의 넓이에서",
        "step4) $\\frac{1}{2}\\times 8\\times 6=\\frac{1}{2}r(10+8+6)$, $24=12r$이다.",
        "step5) $r=2$이므로 내접원의 넓이는 $4\\pi\\,\\mathrm{cm}^2$이다.",
        "step6) 넓이의 차는 $25\\pi-4\\pi=21\\pi\\,(\\mathrm{cm}^2)$이다.",
    ]),
    18: ("$\\frac{15}{2}\\,\\mathrm{cm}^2$", [
        "step1) 정사각형의 한 변의 길이를 $a$라 하면 $a^2=80$이다.",
        "step2) $\\overline{AE}=\\overline{DF}$이므로 $\\overline{AE}+\\overline{AF}=\\overline{DF}+\\overline{AF}=a$이다.",
        "step3) $\\overline{AE}:\\overline{AF}=3:5$이므로 $\\overline{AE}=\\frac{3}{8}a$이다.",
        "step4) 점 $\\mathrm{O}$에서 $\\overline{AB}$까지의 거리는 $\\frac{1}{2}a$이다.",
        "step5) $\\triangle AEO=\\frac{1}{2}\\times\\frac{3}{8}a\\times\\frac{1}{2}a=\\frac{3}{32}a^2$",
        "step6) $\\frac{3}{32}\\times 80=\\frac{15}{2}$이므로 넓이는 $\\frac{15}{2}\\,\\mathrm{cm}^2$이다.",
    ]),
    19: ("$30\\,\\mathrm{cm}$", [
        "step1) $\\overline{AD}\\parallel\\overline{BC}$이므로 $\\angle DAE=\\angle AEB$(엇각)이다.",
        "step2) $\\angle BAE=\\angle DAE$이므로 $\\angle BAE=\\angle AEB$이다.",
        "step3) 따라서 $\\overline{BE}=\\overline{AB}=10\\,\\mathrm{cm}$이다.",
        "step4) $\\angle B=60^\\circ$이므로 $\\triangle ABE$는 정삼각형이고 $\\overline{AE}=10\\,\\mathrm{cm}$이다.",
        "step5) $\\overline{EC}=15-10=5\\,(\\mathrm{cm})$이다.",
        "step6) 같은 방법으로 $\\overline{CF}=10\\,\\mathrm{cm}$, $\\overline{AF}=5\\,\\mathrm{cm}$이다.",
        "step7) 둘레의 길이는 $10+5+10+5=30\\,(\\mathrm{cm})$이다.",
    ]),
    20: ("$9^\\circ$", [
        "step1) $\\angle B=\\angle C=\\frac{1}{2}(180^\\circ-72^\\circ)=54^\\circ$이다.",
        "step2) 점 $\\mathrm{I}$는 내심이므로 $\\angle ICB=\\frac{1}{2}\\times 54^\\circ=27^\\circ$이다.",
        "step3) 점 $\\mathrm{O}$는 외심이므로 $\\angle BOC=2\\angle A=144^\\circ$이다.",
        "step4) $\\overline{OB}=\\overline{OC}$이므로 $\\angle OCB=\\frac{1}{2}(180^\\circ-144^\\circ)=18^\\circ$이다.",
        "step5) $\\angle ICO=27^\\circ-18^\\circ=9^\\circ$이다.",
    ]),
    21: ("$4\\,\\mathrm{cm}$", [
        "step1) $\\triangle ABD$와 $\\triangle CAE$에서 $\\angle ADB=\\angle CEA=90^\\circ$이다.",
        "step2) $\\overline{AB}=\\overline{CA}$이다.",
        "step3) $\\angle BAD=90^\\circ-\\angle CAE=\\angle ACE$이다.",
        "step4) 따라서 $\\triangle ABD\\equiv\\triangle CAE$ (RHA 합동)이다.",
        "step5) $\\overline{AD}=\\overline{CE}=3\\,\\mathrm{cm}$, $\\overline{AE}=\\overline{BD}=7\\,\\mathrm{cm}$이다.",
        "step6) $\\overline{DE}=\\overline{AE}-\\overline{AD}=7-3=4\\,(\\mathrm{cm})$이다.",
    ]),
}

for f in sorted(OCR.glob("p*_merged.json")):
    d = json.loads(f.read_text(encoding="utf-8"))
    for q in d["questions"]:
        n = q["number"]
        if n in MC:
            q["answer"] = MC[n]
            q.pop("solution", None)
        else:
            ans, sol = ESSAY[n]
            q["answer"] = ans
            q["solution"] = "\n".join(sol)
    f.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    json.loads(f.read_text(encoding="utf-8"))
print("ok")
