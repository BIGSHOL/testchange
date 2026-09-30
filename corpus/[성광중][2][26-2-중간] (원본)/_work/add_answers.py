# -*- coding: utf-8 -*-
"""정답·해설 기입(세션 풀이, API 0원)."""
import glob
import json
import os

D = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MC = {1: "③", 2: "③", 3: "②", 4: "④", 5: "⑤", 6: "①", 7: "②", 8: "①", 9: "④",
      10: "②", 11: "③", 12: "④", 13: "⑤", 14: "⑤", 15: "③", 16: "①", 17: "①",
      18: "②"}

ESSAY = {
    19: ("$3\\,\\mathrm{cm}$", [
        "step1) $\\triangle ABC$의 넓이는 $\\frac{1}{2}\\times 15\\times 8=60$ $(\\mathrm{cm}^2)$이다.",
        "step2) 반지름을 $r$라 하면 $\\triangle ABC=\\frac{1}{2}r(15+17+8)=20r$이다.",
        "step3) $20r=60$이므로 $r=3$이다.",
        "step4) 따라서 내접원 $I$의 반지름의 길이는 $3\\,\\mathrm{cm}$이다.",
    ]),
    21: ("$\\frac{128}{3}$", [
        "step1) 점 $O$는 $\\overline{AC}$, $\\overline{BD}$의 중점이다.",
        "step2) $\\triangle ACD$에서 $\\overline{AE}$, $\\overline{DO}$는 중선이다.",
        "step3) 따라서 두 중선의 교점 $F$는 $\\triangle ACD$의 무게중심이다.",
        "step3) $\\triangle ACD=\\frac{1}{2}\\times 256=128$이다.",
        "step4) 무게중심은 $\\triangle ACD$를 넓이가 같은 $6$개로 나눈다.",
        "step5) $\\square OCEF=\\triangle OCF+\\triangle CEF$이다.",
        "step6) 따라서 $\\square OCEF=\\frac{2}{6}\\times 128=\\frac{128}{3}$이다.",
    ]),
    22: ("평행사변형", [
        "step1) $\\overline{AP}=\\overline{BQ}=\\overline{CR}=\\overline{DS}=k$라 하자.",
        "step2) $\\triangle APQ$와 $\\triangle CRS$에서 $\\overline{AP}=\\overline{CR}=k$이다.",
        "step3) $\\overline{AQ}=\\overline{AB}+k=\\overline{CD}+k=\\overline{CS}$이다.",
        "step4) $\\angle A=\\angle C$이므로 $\\angle PAQ=\\angle RCS$이다.",
        "step5) $\\triangle APQ\\equiv\\triangle CRS$(SAS 합동)이므로 $\\overline{PQ}=\\overline{RS}$이다.",
        "step6) 같은 방법으로 $\\triangle BQR\\equiv\\triangle DSP$이므로 $\\overline{QR}=\\overline{SP}$이다.",
        "step7) 두 쌍의 대변의 길이가 각각 같으므로 $\\square PQRS$는 평행사변형이다.",
    ]),
}

SUB20 = {
    1: ("$90^\\circ$", [
        "step1) 점 $P$가 내심이면 $\\overline{PA}$, $\\overline{PB}$, $\\overline{PC}$는 세 내각의 이등분선이다.",
        "step2) 따라서 $\\angle A=2\\angle x$, $\\angle B=2\\angle y$, $\\angle C=2\\angle z$이다.",
        "step3) 세 내각의 합이 $180^\\circ$이므로 $2(\\angle x+\\angle y+\\angle z)=180^\\circ$이다.",
        "step4) 따라서 $\\angle x+\\angle y+\\angle z=90^\\circ$이다.",
    ]),
    2: ("$90^\\circ$", [
        "step1) 점 $P$가 외심이면 $\\overline{PA}=\\overline{PB}=\\overline{PC}$이다.",
        "step2) $\\triangle PAB$, $\\triangle PBC$, $\\triangle PCA$는 이등변삼각형이다.",
        "step3) 따라서 $\\angle PBA=\\angle x$, $\\angle PCB=\\angle y$, $\\angle PAC=\\angle z$이다.",
        "step4) 세 내각의 합이 $180^\\circ$이므로 $2(\\angle x+\\angle y+\\angle z)=180^\\circ$이다.",
        "step4) 따라서 $\\angle x+\\angle y+\\angle z=90^\\circ$이다.",
    ]),
}

import re


def _steps(lines):
    body = [re.sub(r"^step\d+\)\s*", "", ln) for ln in lines]
    return "\n".join(f"step{i}) {b}" for i, b in enumerate(body, 1))


for f in sorted(glob.glob(os.path.join(glob.escape(D), "ocr", "p*_merged.json"))):
    data = json.load(open(f, encoding="utf-8"))
    for q in data["questions"]:
        n = q["number"]
        if n in MC:
            q["answer"] = MC[n]
            q.pop("solution", None)
        elif n in ESSAY:
            q["answer"], lines = ESSAY[n]
            q["solution"] = _steps(lines)
        elif n == 20:
            q.pop("answer", None)
            q.pop("solution", None)
            for sq in q["sub_questions"]:
                sq["answer"], lines = SUB20[sq["number"]]
                sq["solution"] = _steps(lines)
        else:
            raise SystemExit(f"미처리 문항 {n}")
    json.dump(data, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("ok")
