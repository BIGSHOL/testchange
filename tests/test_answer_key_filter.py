# -*- coding: utf-8 -*-
"""답지(정답·해설) 페이지 문항 걷어내기 회귀 — stdlib·API 0원.

⭐ 근거(대륜고 공수2 25-2-기말, 사용자 보고 2026-08-20): ``(원본+답)`` PDF 의 답지 2쪽이
문항으로 OCR 되어 봉투에 28문항(진짜 20 + 유령 8)이 실렸다. 유령은 본문에 채점기준을
찍었을 뿐 아니라 서답형 수를 7→15 로 부풀려 정답면 라벨 재부여를 통째로 죽였다.

    python tests/test_answer_key_filter.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.exam_document import (          # noqa: E402
    ContentBlock, ContentType, ExamPage, Question,
    drop_answer_key_pages, drop_answer_key_questions,
)

fails = []


def chk(cond, msg):
    if not cond:
        fails.append("  " + msg)


def _q(number=None, score=None, text="", choices=0, label_type=""):
    q = {"number": number, "score": score,
         "contents": [{"type": "text", "value": text}] if text else []}
    if choices:
        q["choices"] = [{"number": i + 1, "contents": [{"type": "text", "value": "①"}]}
                        for i in range(choices)]
    if label_type:
        q["label_type"] = label_type
    return q


# ── A: 대륜고 재현 — 객관식 13 + 서답형 7 + 답지 조각 8 ──────────────────
mc = [_q(i, 2.3 + i * 0.1, f"객관식 {i}", choices=5) for i in range(1, 14)]
essays = [_q(1, 12, "[서술형1] 두 조건 p…"), _q(2, 12, "[서술형2] 유리함수…"),
          _q(3, 13, "[서술형3] 합성함수…"), _q(4, None, "<상자> 인쇄된 텍스트가 없습니다"),
          _q(5, 3.8, "[단답형5] 집합 X…"), _q(6, 4, "[단답형6] 함수 f…"),
          _q(7, 4.2, "[단답형7] 집합 X…")]
ghosts = [_q(1, None, "두 조건 p, q의 진리집합을 각각…"), _q(2, None, "함수의 그래프가 원점을…"),
          _q(3, None, "(h∘(g∘f))(x) = …"), _q(4, None, "x=0일 때 최솟값 2…"),
          _q(5, None, "g가 f의 역함수이므로…"), _q(6, None, "12개"),
          _q(7, None, "n과 10이 서로소…"), _q(1, 0, "")]
kept, dropped = drop_answer_key_questions(mc + essays + ghosts)
chk(len(kept) == 20, f"A 답지 8개 제외 → 20문항 (실제 {len(kept)})")
chk(len(dropped) == 8, f"A 걷어낸 수 8 (실제 {len(dropped)})")
chk(all(q.get("score") or q.get("choices") or "인쇄된 텍스트" in
        (q["contents"][0]["value"] if q.get("contents") else "") for q in kept),
    "A 남은 문항은 배점/선택지가 있거나 OCR 실패 문항")

# ── B: 정상 시험지는 **한 문항도** 건드리지 않는다(무회귀 핵심) ───────────
for name, doc in (("객관식만", mc),
                  ("객관식+서답형", mc + essays[:3] + essays[4:]),
                  ("서답형만", essays[:3])):
    k, d = drop_answer_key_questions(doc)
    chk(len(k) == len(doc) and not d, f"B 정상({name}) 무변화 — 걷어낸 {len(d)}개")

# ── C: 유형별 독립 번호(정화중형) — 번호가 중복돼도 배점/라벨이 있으면 보존 ──
jh = [_q(1, 5, "[단답형 1] …"), _q(2, 5, "[단답형 2] …"), _q(3, 5, "[단답형 3] …"),
      _q(1, 8, "[서술형 1] …"), _q(2, 8, "[서술형 2] …"), _q(3, 8, "[서술형 3] …")]
k, d = drop_answer_key_questions(jh)
chk(len(k) == 6 and not d, f"C 유형별 독립번호 보존 (걷어낸 {len(d)}개)")

# ── D: 배점이 없어도 label_type 이 있으면 진짜 문항 ───────────────────────
noscore = jh[:5] + [_q(3, None, "정답을 구하시오.", label_type="서술형")]
k, d = drop_answer_key_questions(noscore)
chk(len(k) == 6 and not d, f"D label_type 있으면 보존 (걷어낸 {len(d)}개)")

# ── E: 안전 상한 — 절반 이상이 후보면 판정을 통째로 버린다 ────────────────
bad = [_q(1, None, "풀이 조각 1"), _q(1, None, "풀이 조각 2"), _q(2, None, "풀이 조각 3"),
       _q(3, 5, "[서술형 3] 진짜 문항")]
k, d = drop_answer_key_questions(bad)
chk(len(k) == 4 and not d, f"E 절반 초과 판정은 폐기 (걷어낸 {len(d)}개)")

# ── F: 빈 문항은 위치와 무관하게 제거 ────────────────────────────────────
withempty = mc[:2] + [_q(3, 2.5, "")] + mc[2:4]
k, d = drop_answer_key_questions(withempty)
chk(len(k) == 4 and len(d) == 1, f"F 빈 문항 제거 (남은 {len(k)}·걷어낸 {len(d)})")

# ── G: 파싱 후 경로(GUI/exe) — 페이지를 가로질러 같은 규칙 ────────────────
def _Q(number, score, text, choices=0, label_type=""):
    return Question(number=number, score=score, label_type=label_type,
                    contents=[ContentBlock(type=ContentType.TEXT, value=text)],
                    choices=[object()] * choices)   # choices 는 개수만 본다


p1 = ExamPage(page_number=1, questions=[_Q(i, 2.3, f"객관식 {i}", choices=5)
                                        for i in range(1, 4)])
p2 = ExamPage(page_number=2, questions=[_Q(1, 12, "[서술형 1] 문항"),
                                        _Q(2, 12, "[서술형 2] 문항")])
p3 = ExamPage(page_number=3, questions=[_Q(1, None, "두 조건 p…이므로"),
                                        _Q(2, None, "따라서 a=…이다.")])
gone = drop_answer_key_pages([p1, p2, p3])
chk(len(gone) == 2 and not p3.questions,
    f"G 페이지 가로지르기 — 답지 2개 제거 (실제 {len(gone)}, p3 남은 {len(p3.questions)})")
chk(len(p1.questions) == 3 and len(p2.questions) == 2, "G 진짜 페이지 무변화")

# 답지 없는 문서는 무변화(idempotent).
gone2 = drop_answer_key_pages([p1, p2])
chk(not gone2 and len(p1.questions) == 3 and len(p2.questions) == 2, "G 무회귀·멱등")

if fails:
    print("FAIL test_answer_key_filter")
    print("\n".join(fails))
    sys.exit(1)
print("OK test_answer_key_filter (drop/keep/label_type/safety-cap/empty/pages)")
