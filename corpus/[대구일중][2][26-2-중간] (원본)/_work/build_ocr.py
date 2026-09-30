# -*- coding: utf-8 -*-
"""대구일중 중2 26-2-중간 self-OCR JSON 작성(세션 비전 판독, API 0원)."""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "ocr"


def T(v):
    return {"type": "text", "value": v}


def E(v):
    return {"type": "equation", "value": v}


def EB(v):
    return {"type": "equation_block", "value": v}


def F(desc, bbox):
    return {"type": "figure", "value": desc, "bbox": bbox}


def ch(*items):
    out = []
    for i, it in enumerate(items, 1):
        if isinstance(it, list):
            out.append({"number": i, "contents": it})
        else:
            out.append({"number": i, "contents": [E(it)]})
    return out


def deg(*vals):
    return ch(*[f"{v}^{{\\circ}}" for v in vals])


def Q(n, s, contents, choices=None, **kw):
    q = {"number": n, "score": s, "contents": contents}
    if choices:
        q["choices"] = choices
    q.update(kw)
    return q


p3 = [
    Q(1, 3, [E(r"\triangle ABC"), T("에서 "), E(r"\angle x"), T("의 크기는?"),
             F("이등변삼각형 ABC(A 위, B 좌하, C 우하), AB·AC 에 같음 표시(//), 꼭지각 A 70°, "
               "변 BC 를 C 너머로 연장, C 의 외각 x°(각 표시).", [0.3, 0.2, 0.75, 0.68])],
      deg(115, 120, 125, 130, 135)),
    Q(2, 3, [T("두 직각삼각형 ABC와 DEF가 서로 합동이 되기 위한 조건만을 <보기>에서 있는대로 고른 것은?"),
             F("두 직각삼각형 ABC(∠B=90°, A 위, B 좌하, C 우하)와 DEF(∠E=90°, D 위, E 좌하, F 우하), "
               "같은 모양·크기로 나란히, 직각 표시.", [0.6, 0.0, 1.0, 0.27]),
             T(r"<보기> ㄱ. \overline{AC}=\overline{DF}, \overline{BC}=\overline{EF} • "
               r"ㄴ. \overline{AB}=\overline{DE}, \overline{BC}=\overline{DF} • "
               r"ㄷ. \overline{AC}=\overline{DF}, \angle C=\angle F • "
               r"ㄹ. \overline{AB}=\overline{DE}, \angle A=\angle D • "
               r"ㅁ. \angle A=\angle D, \angle C=\angle F")],
      ch([T("ㄱ, ㄷ")], [T("ㄷ, ㄹ")], [T("ㄱ, ㄴ, ㅁ")], [T("ㄱ, ㄷ, ㄹ")], [T("ㄴ, ㄹ, ㅁ")])),
    Q(3, 3, [T("점 I가 "), E(r"\triangle ABC"), T("의 내심일 때, "), E(r"\angle x"), T("의 크기는?"),
             F("삼각형 ABC(A 위, B 좌하, C 우하)와 내심 I, 선분 AI·BI·CI. ∠BAI=35°, ∠IBC=25°, ∠ICB=x°.",
               [0.2, 0.1, 0.72, 0.68])],
      deg(25, 30, 35, 40, 45)),
    Q(4, 3, [T("점 O가 "), E(r"\triangle ABC"), T("의 외심일 때, "), E(r"\angle x"), T("의 크기는?"),
             F("삼각형 ABC(A 위, B 좌하, C 우하)와 외심 O(삼각형 안), 선분 OA·OC. ∠AOC=110°, ∠ABC=x°.",
               [0.25, 0.15, 0.78, 0.72])],
      deg(35, 40, 45, 50, 55)),
    Q(5, 3, [E(r"\square ABCD"), T("가 평행사변형이 "), T("__아닌__"),
             T(" 것은? (단, 점 O는 두 대각선의 교점이다.)")],
      ch(r"\overline{AD}\parallel \overline{BC}, \angle B=50^{\circ}, \angle C=130^{\circ}",
         r"\overline{AB}=\overline{CD}=4\mathrm{cm}, \overline{AD}=\overline{BC}=6\mathrm{cm}",
         r"\angle A=100^{\circ}, \angle B=80^{\circ}, \angle C=100^{\circ}",
         r"\overline{OA}=\overline{OC}=5\mathrm{cm}, \overline{OB}=\overline{OD}=7\mathrm{cm}",
         r"\overline{AB}=\overline{CD}=13\mathrm{cm}, \angle A=80^{\circ}, \angle B=100^{\circ}")),
    Q(6, 3, [T("마름모 ABCD에서 "), E("x+y"), T("의 값은?"),
             F("마름모 ABCD(A 위, B 왼쪽, C 아래, D 오른쪽), 대각선 AC·BD 의 교점 O. ∠OAD=55°, "
               "∠ABO=y°(음영), OD 위 점선 치수 8 cm, BO 아래 점선 치수 x cm.", [0.2, 0.15, 0.8, 0.7])],
      ch("38", "43", "52", "68", "76")),
]

p4 = [
    Q(7, 4, [T("점 O는 "), E(r"\triangle ABC"), T("의 외심이다. "), E(r"\overline{AD}=6\mathrm{cm}"),
             T(", "), E(r"\overline{OD}=4\mathrm{cm}"), T(", "), E(r"\triangle ABC=50\mathrm{cm}^{2}"),
             T("일 때, 사각형 OECF의 넓이는?"),
             F("삼각형 ABC(A 위, B 좌하, C 우하)와 외심 O. O에서 AB·BC·CA 에 내린 수선의 발 D·E·F(직각 표시). "
               "선분 OA·OB·OC(가는 선). 사각형 OECF 음영. A~D 점선 6cm, D~O 점선 4cm.",
               [0.25, 0.2, 0.75, 0.75])],
      ch(r"13\mathrm{cm}^{2}", r"14\mathrm{cm}^{2}", r"15\mathrm{cm}^{2}", r"16\mathrm{cm}^{2}",
         r"17\mathrm{cm}^{2}")),
    Q(8, 4, [E(r"\triangle ABC"), T("에서 점 C는 "), E(r"\overline{AD}"), T(" 위에 있고, "),
             E(r"\overline{AB}=\overline{BC}=\overline{CD}"), T("일 때, "), E(r"\angle x"), T("의 크기는?"),
             F("A, C, D 가 한 직선(위쪽 수평) 위에 있고 B 는 아래. AB=BC=CD(같음 표시), 선분 DB 를 B 너머로 연장, "
               "B 의 외각(연장선과 BA 사이) 132°, ∠ADB=x.", [0.25, 0.25, 0.68, 0.62])],
      deg(41, 42, 43, 44, 45)),
    Q(9, 4, [T("점 I는 "), E(r"\triangle ABC"), T("의 내심이고, "), E(r"\overline{DE}\parallel \overline{BC}"),
             T("이다. "), E(r"\angle ADI=70^{\circ}"), T(", "), E(r"\angle ECI=21^{\circ}"), T("일 때, "),
             E(r"\angle DIB+\angle AEI"), T("의 크기는?"),
             F("삼각형 ABC(A 위, B 좌하, C 우하), 내심 I 를 지나 BC 에 평행한 선분 DE(D 는 AB 위, E 는 AC 위), "
               "선분 BI·CI. ∠ADI=70°, ∠ECI=21°(지시선), ∠AEI 각 표시.", [0.2, 0.2, 0.75, 0.68])],
      deg(77, 78, 79, 80, 81)),
    Q(10, 4, [T("그림과 같은 평행사변형 ABCD에 대한 설명으로 옳지 "), T("__않은__"), T(" 것은?"),
              F("평행사변형 ABCD(A 좌상, D 우상, B 좌하, C 우하), 두 대각선 AC·BD 의 교점 O.",
                [0.2, 0.18, 0.65, 0.5])],
      ch([E(r"\overline{AC}\perp\overline{BD}"), T(" 이면 사각형 ABCD는 마름모이다.")],
         [E(r"\overline{AC}=\overline{BC}"), T(" 이면 사각형 ABCD는 마름모이다.")],
         [E(r"\overline{AC}=\overline{BD}"), T(" 이면 사각형 ABCD는 직사각형이다.")],
         [E(r"\angle ABO=\angle ADO"), T(" 이면 사각형 ABCD는 마름모이다.")],
         [E(r"\angle DAB=\angle ADC"), T(" 이면 사각형 ABCD는 직사각형이다.")])),
    Q(11, 4, [T("다음은 '평행사변형의 두 대각선은 서로 다른 것을 이등분한다.'를 설명하는 과정이다. "
                "두 대각선의 교점을 O라고 할 때, (가)~(마)에 들어갈 내용이 바르게 나열된 것은?"),
              F("평행사변형 ABCD(A 좌상, D 우상, B 좌하, C 우하), 대각선 AC·BD 의 교점 O. "
                "∠BAO 와 ∠DCO(엇각), ∠ABO 와 ∠CDO 에 각 표시.", [0.3, 0.18, 0.7, 0.34]),
              T(r"<상자> \triangle AOB와 \triangle COD에서 • \overline{AB}\parallel \overline{DC}이므로 • "
                r"\angle ABO=\boxed{가} (엇각) ⋯⋯ ① • \angle BAO=\boxed{나} (엇각) ⋯⋯ ② • "
                r"또, 평행사변형의 성질에 의해 • \overline{AB}=\boxed{다} ⋯⋯ ③ • "
                r"①, ②, ③에서 \triangle AOB\equiv\boxed{라} (\boxed{마} 합동) • "
                r"이므로 \overline{OA}=\overline{OC}, \overline{OB}=\overline{OD}")],
      ch([T("(가) "), E(r"\angle CBO"), T(", (나) "), E(r"\angle DOC"), T(", (다) "), E(r"\overline{CD}"),
          T(", (라) "), E(r"\triangle COD"), T(", (마) ASA")],
         [T("(가) "), E(r"\angle CBO"), T(", (나) "), E(r"\angle DOC"), T(", (다) "), E(r"\overline{BC}"),
          T(", (라) "), E(r"\triangle BOC"), T(", (마) SAS")],
         [T("(가) "), E(r"\angle CDO"), T(", (나) "), E(r"\angle DCO"), T(", (다) "), E(r"\overline{CD}"),
          T(", (라) "), E(r"\triangle COD"), T(", (마) ASA")],
         [T("(가) "), E(r"\angle CDO"), T(", (나) "), E(r"\angle DCO"), T(", (다) "), E(r"\overline{CD}"),
          T(", (라) "), E(r"\triangle COD"), T(", (마) SAS")],
         [T("(가) "), E(r"\angle COD"), T(", (나) "), E(r"\angle DAO"), T(", (다) "), E(r"\overline{BC}"),
          T(", (라) "), E(r"\triangle BOC"), T(", (마) ASA")])),
]

p5 = [
    Q(12, 4, [T("그림과 같은 직사각형 ABCD에서 점 A가 점 C와 겹치도록 접을 때, "), E(r"\angle x"),
              T("의 크기는?"),
              F("직사각형 ABCD(A 좌상, D 우상, B 좌하, C 우하)를 접는 선 EF(E 는 AD 위, F 는 BC 위)로 접어 "
                "A 가 C 에 겹침. 접힌 부분 ABFE 의 원래 자리는 점선(A·B 쪽). 접혀 넘어간 B 의 상 G(아래). "
                "∠EFC=x°, ∠FCG=26°.", [0.2, 0.25, 0.8, 0.85])],
      deg(54, 55, 56, 57, 58)),
    Q(13, 4, [T("그림의 평행사변형 ABCD의 두 꼭짓점 B, D에서 대각선 "), E(r"\overline{AC}"),
              T("위에 내린 수선의 발을 각각 E, F라고 하고 대각선의 교점을 O라고 할 때, 옳은 것만을 <보기>에서 고른 것은?"),
              F("평행사변형 ABCD(A 좌상, D 우상, B 좌하, C 우하), 대각선 AC·BD 교점 O. B 에서 AC 에 내린 수선의 발 E, "
                "D 에서 AC 에 내린 수선의 발 F(직각 표시). 선분 BF·DE.", [0.25, 0.18, 0.78, 0.44]),
              T(r"<보기> ㄱ. \overline{BE}=\overline{FD} • ㄴ. \overline{ED}=\overline{FD} • "
                r"ㄷ. \overline{BD}\perp\overline{EF} • ㄹ. \angle BFO=\angle DEO • "
                r"ㅁ. \triangle EDO\equiv\triangle FDO • ㅂ. \triangle EBO\equiv\triangle FDO")],
      ch([T("ㄱ, ㄴ, ㄹ")], [T("ㄱ, ㄹ, ㅂ")], [T("ㄴ, ㄷ, ㅁ")], [T("ㄷ, ㅁ, ㅂ")], [T("ㄹ, ㅁ, ㅂ")])),
    Q(14, 4, [T("두 점 O와 I는 각각 "), E(r"\overline{AB}=\overline{AC}"), T("인 이등변삼각형 "),
              E(r"\triangle ABC"), T("의 외심과 내심이다. "), E(r"\angle A=80^{\circ}"), T("이고 "),
              E(r"\overline{AC}"), T("의 중점을 D, "), E(r"\overline{OD}"), T("와 "), E(r"\overline{IC}"),
              T("의 교점을 E라 할 때, "), E(r"\angle DEC"), T("의 크기는?"),
              F("이등변삼각형 ABC(A 위, B 좌하, C 우하), ∠A=80°. 내심 I, 외심 O(I 아래). 선분 IC, "
                "AC 의 중점 D 와 O 를 잇는 선분 OD, OD 와 IC 의 교점 E, ∠DEC 각 표시.", [0.2, 0.28, 0.72, 0.78])],
      deg(63, 64, 65, 66, 67)),
    Q(15, 5, [T("사각형 ABCD의 꼭짓점 A를 지나고 "), E(r"\overline{DC}"), T("와 평행한 직선이 "),
              E(r"\overline{BC}"), T("와 만나는 점을 E라고 하자. "), E(r"\overline{AF}=6\mathrm{cm}"), T(", "),
              E(r"\overline{BE}=8\mathrm{cm}"), T(", "), E(r"\overline{EC}=5\mathrm{cm}"), T("일 때, "),
              E(r"\square ABED"), T("의 넓이는?"),
              F("사각형 ABCD 와 AE∥DC(화살표 표시), E 는 BC 위. A 에서 BC 에 내린 수선의 발 F(직각 표시). "
                "사각형 ABED 음영. AF 점선 6cm, B~E 점선 8cm, E~C 점선 5cm.", [0.15, 0.3, 0.8, 0.65])],
      ch(r"19\mathrm{cm}^{2}", r"24\mathrm{cm}^{2}", r"36\mathrm{cm}^{2}", r"39\mathrm{cm}^{2}",
         r"48\mathrm{cm}^{2}")),
    Q(16, 5, [T("그림과 같이 "), E(r"\overline{AD}\parallel \overline{BC}"), T("인 등변사다리꼴 ABCD에서 "),
              E(r"\overline{AD}=\overline{CD}"), T(", "), E(r"\overline{AC}=\overline{BC}"), T("일 때, "),
              E(r"\angle DAC"), T("의 크기는?"),
              F("등변사다리꼴 ABCD(윗변 AD, 아랫변 BC), 대각선 AC. AD=CD(두 줄 표시), AC=BC(한 줄 표시), "
                "∠DAC 각 표시.", [0.2, 0.3, 0.72, 0.75])],
      deg(12, 15, 24, 36, 38)),
]

S = "서답형"
p6 = [
    Q(17, 7, [T("[서답형 1] 직각삼각형 ABC에서 외접원의 넓이와 내접원의 넓이의 차를 구하시오."),
              F("직각삼각형 ABC(∠C=90°, 직각 표시)와 외접원·내접원. AB 점선 10cm, AC 점선 6cm, BC 점선 8cm.",
                [0.2, 0.25, 0.7, 0.88])], label_type=S),
    Q(18, 8, [T("[서답형 2] 넓이가 "), E(r"80\mathrm{cm}^{2}"), T("인 정사각형 ABCD에서 "),
              E(r"\overline{AB}"), T(", "), E(r"\overline{AD}"), T(" 위에 "), E(r"\overline{AE}=\overline{DF}"),
              T("가 되는 점 E, F가 있다. "), E(r"\overline{AE}:\overline{AF}=3:5"), T(" 일 때, "),
              E(r"\triangle AEO"), T("의 넓이를 구하시오. (단, 점 O는 정사각형 ABCD의 교점이다.)"),
              F("정사각형 ABCD(A 좌상, D 우상, B 좌하, C 우하), 두 대각선 교점 O. E 는 AB 위, F 는 AD 위, "
                "선분 OE·OF. AE·FD 에 같음 표시. 삼각형 AEO 음영.", [0.25, 0.4, 0.72, 0.9])], label_type=S),
    Q(19, 8, [T("[서답형 3] 평행사변형 ABCD에서 "), E(r"\overline{AE}"), T(", "), E(r"\overline{CF}"),
              T("는 각각 "), E(r"\angle A"), T(", "), E(r"\angle C"), T("의 이등분선이다. "),
              E(r"\angle ABC=60^{\circ}"), T("이고, "), E(r"\overline{AB}=10\mathrm{cm}"), T(", "),
              E(r"\overline{AD}=15\mathrm{cm}"), T("일 때, "), E(r"\square AECF"), T("의 둘레의 길이를 구하시오."),
              F("평행사변형 ABCD(A 좌상, D 우상, B 좌하, C 우하), ∠B=60°. E 는 BC 위, F 는 AD 위, "
                "선분 AE·CF(∠A 의 두 부분에 점 표시, ∠C 의 두 부분에 × 표시). A~D 점선 15 cm, B~A 점선 10 cm.",
                [0.2, 0.42, 0.72, 0.92])], label_type=S),
    Q(20, 8, [T("[서답형 4] "), E(r"\triangle ABC"), T("는 "), E(r"\overline{AB}=\overline{AC}"),
              T("인 이등변삼각형이다. 점 O는 "), E(r"\triangle ABC"), T("의 외심이고, 점 I는 "),
              E(r"\triangle ABC"), T("의 내심일 때, "), E(r"\angle ICO"), T("의 크기를 구하시오."),
              F("이등변삼각형 ABC(A 위, B 좌하, C 우하), ∠A=72°. 내심 I, 외심 O(I 아래), 선분 BI·CI·BO·CO, "
                "∠ICO 각 표시.", [0.18, 0.3, 0.75, 0.85])], label_type=S),
    Q(21, 9, [T("[서답형 5] "), E(r"\overline{AB}=\overline{AC}"),
              T("인 직각삼각형 ABC에서 꼭짓점 A를 지나는 직선 "), E("l"), T("을 그었다. 두 꼭짓점 B, C에서 직선 "),
              E("l"), T("에 내린 수선의 발을 각각 D, E라고 할 때, 합동인 두 삼각형을 찾아 합동인 이유를 설명하고 "),
              E(r"\overline{DE}"), T("의 길이를 구하시오."),
              F("직각이등변삼각형 ABC(∠A=90°, A 위, B 좌하, C 우하, AB=AC 같음 표시), A 를 지나는 직선 l(좌상→우하), "
                "l 과 BC 의 교점 F. B·C 에서 l 에 내린 수선의 발 D·E(직각 표시). BD 점선 7cm, CE 점선 3cm.",
                [0.18, 0.4, 0.75, 0.98])], label_type=S),
]

for n, qs in ((3, p3), (4, p4), (5, p5), (6, p6)):
    (OUT / f"p{n}_merged.json").write_text(
        json.dumps({"header": "", "questions": qs}, ensure_ascii=False, indent=1), encoding="utf-8")
tot = sum(q["score"] for qs in (p3, p4, p5, p6) for q in qs)
print("questions", sum(len(x) for x in (p3, p4, p5, p6)), "score", tot)
