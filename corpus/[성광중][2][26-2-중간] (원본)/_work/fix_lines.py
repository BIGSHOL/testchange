# -*- coding: utf-8 -*-
import os
p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "add_answers.py")
s = open(p, encoding="utf-8").read()
R = [
    ('''        "step2) 내접원의 반지름을 $r\\\\,\\\\mathrm{cm}$라 하면",
        "$\\\\triangle ABC=\\\\frac{1}{2}r(15+17+8)=20r$이다.",''',
     '''        "step2) 반지름을 $r$라 하면 $\\\\triangle ABC=\\\\frac{1}{2}r(15+17+8)=20r$이다.",'''),
    ('''        "step2) $\\\\triangle ACD$에서 $\\\\overline{AE}$, $\\\\overline{DO}$는 중선이므로",
        "그 교점 $F$는 $\\\\triangle ACD$의 무게중심이다.",''',
     '''        "step2) $\\\\triangle ACD$에서 $\\\\overline{AE}$, $\\\\overline{DO}$는 중선이다.",
        "step3) 따라서 두 중선의 교점 $F$는 $\\\\triangle ACD$의 무게중심이다.",'''),
    ('''        "step4) 무게중심과 세 꼭짓점, 세 변의 중점을 이으면",
        "넓이가 같은 삼각형 $6$개로 나뉜다.",
        "step5) $\\\\square OCEF=\\\\triangle OCF+\\\\triangle CEF$",
        "$=\\\\frac{2}{6}\\\\times 128=\\\\frac{128}{3}$이다.",''',
     '''        "step4) 무게중심은 $\\\\triangle ACD$를 넓이가 같은 $6$개로 나눈다.",
        "step5) $\\\\square OCEF=\\\\triangle OCF+\\\\triangle CEF$이다.",
        "step6) 따라서 $\\\\square OCEF=\\\\frac{2}{6}\\\\times 128=\\\\frac{128}{3}$이다.",'''),
    ('''        "step2) $\\\\triangle APQ$와 $\\\\triangle CRS$에서 $\\\\overline{AP}=\\\\overline{CR}=k$,",
        "$\\\\overline{AQ}=\\\\overline{AB}+k=\\\\overline{CD}+k=\\\\overline{CS}$이다.",
        "step3) $\\\\angle PAQ=180^\\\\circ-\\\\angle A$, $\\\\angle RCS=180^\\\\circ-\\\\angle C$이고",
        "$\\\\angle A=\\\\angle C$이므로 $\\\\angle PAQ=\\\\angle RCS$이다.",
        "step4) 따라서 $\\\\triangle APQ\\\\equiv\\\\triangle CRS$ (SAS 합동)이므로",
        "$\\\\overline{PQ}=\\\\overline{RS}$이다.",
        "step5) 같은 방법으로 $\\\\triangle BQR\\\\equiv\\\\triangle DSP$ (SAS 합동)이므로",
        "$\\\\overline{QR}=\\\\overline{SP}$이다.",
        "step6) 두 쌍의 대변의 길이가 각각 같으므로",
        "$\\\\square PQRS$는 평행사변형이다.",''',
     '''        "step2) $\\\\triangle APQ$와 $\\\\triangle CRS$에서 $\\\\overline{AP}=\\\\overline{CR}=k$이다.",
        "step3) $\\\\overline{AQ}=\\\\overline{AB}+k=\\\\overline{CD}+k=\\\\overline{CS}$이다.",
        "step4) $\\\\angle A=\\\\angle C$이므로 $\\\\angle PAQ=\\\\angle RCS$이다.",
        "step5) $\\\\triangle APQ\\\\equiv\\\\triangle CRS$(SAS 합동)이므로 $\\\\overline{PQ}=\\\\overline{RS}$이다.",
        "step6) 같은 방법으로 $\\\\triangle BQR\\\\equiv\\\\triangle DSP$이므로 $\\\\overline{QR}=\\\\overline{SP}$이다.",
        "step7) 두 쌍의 대변의 길이가 각각 같으므로 $\\\\square PQRS$는 평행사변형이다.",'''),
    ('''        "step1) 점 $P$가 내심이면 $\\\\overline{PA}$, $\\\\overline{PB}$, $\\\\overline{PC}$는",
        "각각 $\\\\angle A$, $\\\\angle B$, $\\\\angle C$의 이등분선이다.",''',
     '''        "step1) 점 $P$가 내심이면 $\\\\overline{PA}$, $\\\\overline{PB}$, $\\\\overline{PC}$는 세 내각의 이등분선이다.",'''),
    ('''        "step3) 삼각형의 세 내각의 합은 $180^\\\\circ$이므로",
        "$2(\\\\angle x+\\\\angle y+\\\\angle z)=180^\\\\circ$이다.",''',
     '''        "step3) 세 내각의 합이 $180^\\\\circ$이므로 $2(\\\\angle x+\\\\angle y+\\\\angle z)=180^\\\\circ$이다.",'''),
    ('''        "step2) $\\\\triangle PAB$, $\\\\triangle PBC$, $\\\\triangle PCA$는 이등변삼각형이므로",
        "$\\\\angle PBA=\\\\angle x$, $\\\\angle PCB=\\\\angle y$, $\\\\angle PAC=\\\\angle z$이다.",
        "step3) $\\\\triangle ABC$의 세 내각의 합은 $180^\\\\circ$이므로",
        "$2(\\\\angle x+\\\\angle y+\\\\angle z)=180^\\\\circ$이다.",''',
     '''        "step2) $\\\\triangle PAB$, $\\\\triangle PBC$, $\\\\triangle PCA$는 이등변삼각형이다.",
        "step3) 따라서 $\\\\angle PBA=\\\\angle x$, $\\\\angle PCB=\\\\angle y$, $\\\\angle PAC=\\\\angle z$이다.",
        "step4) 세 내각의 합이 $180^\\\\circ$이므로 $2(\\\\angle x+\\\\angle y+\\\\angle z)=180^\\\\circ$이다.",'''),
]
for a, b in R:
    pass
    pass
    n = s.count(a)
    assert n >= 1, a[:60]
    s = s.replace(a, b)
open(p, "w", encoding="utf-8").write(s)
print("fixed")
