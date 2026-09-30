# -*- coding: utf-8 -*-
"""산격중2 26-2-중간 — 정답(객관식 원문자) + 서답형 소문항 정답·해설 기입."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
MC = {1: "④", 2: "④", 3: "②", 4: "⑤", 5: "②", 6: "⑤", 7: "④", 8: "②", 9: "①",
      10: "①", 11: "③", 12: "③", 13: "③", 14: "⑤", 15: "③", 16: "⑤", 17: "①"}

ESSAY = {
    18: {
        1: ("반지름 $2\\,\\mathrm{cm}$, 넓이 $4\\pi\\,\\mathrm{cm}^{2}$", [
            "내접원의 반지름을 $r\\,\\mathrm{cm}$라 하자.",
            "$\\triangle ABC$의 넓이는 $\\frac{1}{2}\\times 6\\times 8=24$이다.",
            "내심에서 세 변까지의 거리가 모두 $r$이므로",
            "$\\triangle ABC=\\frac{1}{2}r(10+6+8)=12r$이다.",
            "$12r=24$이므로 $r=2$이다.",
            "따라서 내접원의 넓이는 $\\pi\\times 2^{2}=4\\pi\\,(\\mathrm{cm}^{2})$이다.",
        ]),
        2: ("외심은 $\\overline{AB}$의 중점, 넓이 $25\\pi\\,\\mathrm{cm}^{2}$", [
            "직각삼각형의 외심은 빗변의 중점이다.",
            "$\\angle C=90^{\\circ}$이므로 외심은 빗변 $\\overline{AB}$의 중점이다.",
            "외접원의 반지름은 $\\frac{1}{2}\\overline{AB}=\\frac{1}{2}\\times 10=5$이다.",
            "따라서 외접원의 넓이는 $\\pi\\times 5^{2}=25\\pi\\,(\\mathrm{cm}^{2})$이다.",
        ]),
    },
    19: {
        1: ("$\\triangle ABC\\equiv\\triangle DCB$ (SSS 합동)", [
            "평행사변형의 대변의 길이는 같으므로 $\\overline{AB}=\\overline{DC}$이다.",
            "두 대각선의 길이가 같으므로 $\\overline{AC}=\\overline{DB}$이다.",
            "$\\overline{BC}$는 공통인 변이다.",
            "세 쌍의 대응변의 길이가 각각 같으므로",
            "$\\triangle ABC\\equiv\\triangle DCB$ (SSS 합동)이다.",
        ]),
        2: ("$\\square ABCD$의 네 내각이 모두 $90^{\\circ}$이므로 직사각형이다.", [
            "(1)에서 $\\triangle ABC\\equiv\\triangle DCB$이므로",
            "$\\angle ABC=\\angle DCB$이다.",
            "평행사변형에서 이웃한 두 내각의 합은 $180^{\\circ}$이므로",
            "$\\angle ABC+\\angle DCB=180^{\\circ}$이다.",
            "따라서 $\\angle ABC=\\angle DCB=90^{\\circ}$이다.",
            "평행사변형의 대각의 크기는 같으므로",
            "$\\angle A=\\angle C=90^{\\circ}$, $\\angle D=\\angle B=90^{\\circ}$이다.",
            "네 내각의 크기가 모두 같으므로 $\\square ABCD$는 직사각형이다.",
        ]),
    },
    20: {
        1: ("두 쌍의 대변의 길이가 각각 같다.", [
            "$\\overline{AD}=\\overline{BC}=9\\,\\mathrm{cm}$이다.",
            "$\\overline{AB}=\\overline{DC}=7\\,\\mathrm{cm}$이다.",
            "두 쌍의 대변의 길이가 각각 같으므로 평행사변형이다.",
        ]),
        2: ("두 쌍의 대각의 크기가 각각 같다.", [
            "$\\angle A=360^{\\circ}-(50^{\\circ}+130^{\\circ}+50^{\\circ})=130^{\\circ}$이다.",
            "$\\angle A=\\angle C=130^{\\circ}$, $\\angle B=\\angle D=50^{\\circ}$이다.",
            "두 쌍의 대각의 크기가 각각 같으므로 평행사변형이다.",
        ]),
        3: ("한 쌍의 대변이 평행하고 그 길이가 같다.", [
            "$\\overline{AD}\\,/\\!/\\,\\overline{BC}$이다.",
            "$\\overline{AD}=\\overline{BC}=4\\,\\mathrm{cm}$이다.",
            "한 쌍의 대변이 평행하고 그 길이가 같으므로 평행사변형이다.",
        ]),
        4: ("두 대각선이 서로 다른 것을 이등분한다.", [
            "두 대각선의 교점 $O$에 대하여 $\\overline{OA}=\\overline{OC}=3\\,\\mathrm{cm}$이다.",
            "같은 방법으로 $\\overline{OB}=\\overline{OD}$이다.",
            "두 대각선이 서로 다른 것을 이등분하므로 평행사변형이다.",
        ]),
        5: ("두 쌍의 대변이 각각 평행한 사각형", [
            "평행사변형은 두 쌍의 대변이 각각 평행한 사각형이다.",
            "즉, $\\overline{AB}\\,/\\!/\\,\\overline{DC}$, $\\overline{AD}\\,/\\!/\\,\\overline{BC}$이다.",
        ]),
    },
    21: {
        1: ("$\\overline{BD}=4\\,\\mathrm{cm}$", [
            "정사각형의 두 대각선은 길이가 같다.",
            "또 두 대각선은 서로 다른 것을 이등분한다.",
            "$\\overline{AC}=2\\overline{OA}=2\\times 2=4\\,(\\mathrm{cm})$이다.",
            "따라서 $\\overline{BD}=\\overline{AC}=4\\,\\mathrm{cm}$이다.",
        ]),
        2: ("$\\angle BAO=45^{\\circ}$", [
            "정사각형의 두 대각선은 서로 다른 것을 수직이등분한다.",
            "$\\overline{OA}=\\overline{OB}$이고 $\\angle AOB=90^{\\circ}$이다.",
            "$\\triangle OAB$는 직각이등변삼각형이다.",
            "따라서 $\\angle BAO=\\frac{1}{2}\\times 90^{\\circ}=45^{\\circ}$이다.",
        ]),
        3: ("$8\\,\\mathrm{cm}^{2}$", [
            "두 대각선이 서로 수직이므로",
            "넓이는 $\\frac{1}{2}\\times\\overline{AC}\\times\\overline{BD}$이다.",
            "$\\frac{1}{2}\\times 4\\times 4=8\\,(\\mathrm{cm}^{2})$이다.",
        ]),
    },
}


def main():
    for f in sorted((HERE / "ocr").glob("p*_merged.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        for q in d["questions"]:
            n = q["number"]
            if n in MC:
                q["answer"] = MC[n]
                q.pop("solution", None)
            elif n in ESSAY:
                subs = ESSAY[n]
                parts, all_steps = [], []
                for s in q["sub_questions"]:
                    ans, steps = subs[s["number"]]
                    s["answer"] = ans
                    s["solution"] = "\n".join(f"step{i}) {t}" for i, t in enumerate(steps, 1))
                    parts.append(f"({s['number']}) {ans}")
                    all_steps += [f"({s['number']}) {steps[0]}"] + steps[1:]
                # 폼 정답면은 부모 문항의 answer/solution 만 읽는다(hwp_form_writer 1.55·1.56단계)
                # → 소문항 것을 모아 부모에도 둔다(소문항 번호 머리 + 연속 step).
                q["answer"] = "  ".join(parts)
                q["solution"] = "\n".join(f"step{i}) {t}" for i, t in enumerate(all_steps, 1))
            else:
                raise SystemExit(f"unknown question {n}")
        f.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print("ok")


if __name__ == "__main__":
    main()
