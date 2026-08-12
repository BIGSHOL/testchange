# -*- coding: utf-8 -*-
"""문제 DB 내용 무결성 감사

파서 통과·JSON 유효성만으로는 못 잡는 결함을 본다. 병렬 OCR 은 **그럴듯하게 틀린**
결과를 낼 수 있어(다른 시험지 오염 등) 형식이 아니라 내용 정합으로 걸러야 한다.

  python db/audit.py            전체 감사
  python db/audit.py --exam 4209
  python db/audit.py --strict   경고도 실패로 취급(CI 게이트용)
"""
from __future__ import annotations
import argparse, json, re, sqlite3, sys, io, pathlib, collections

BASE = pathlib.Path(__file__).parent
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
DB = BASE / "exam_index.db"
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"


def blocks_of(q: dict):
    out = list(q.get("contents") or [])
    for ch in q.get("choices") or []:
        out += list(ch.get("contents") or [])
    for s in q.get("sub_questions") or []:
        out += list(s.get("contents") or [])
    return out


def latex_balanced(s: str) -> bool:
    """중괄호·$ 균형. 이스케이프된 \\{ \\} 는 제외."""
    t = re.sub(r"\\[{}$]", "", s or "")
    if t.count("$") % 2:
        return False
    depth = 0
    for c in t:
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def audit_exam(eid, school, tag, rows, errs, warns):
    nums = [r["number"] for r in rows]
    # 번호 중복·결번
    dup = [n for n, c in collections.Counter(nums).items() if c > 1]
    if dup:
        errs.append(f"{tag}: 문항번호 중복 {dup}")
    if nums:
        gaps = sorted(set(range(min(nums), max(nums) + 1)) - set(nums))
        if gaps:
            warns.append(f"{tag}: 번호 결번 {gaps[:10]}")

    score_sum = 0.0
    for r in rows:
        q = json.loads(r["ocr_json"])
        n = r["number"]
        where = f"{tag} #{n}"

        # 발문 비어 있음
        txt = "".join((b.get("value") or "") for b in (q.get("contents") or []))
        if not txt.strip():
            errs.append(f"{where}: 발문 비어 있음")

        # 선택지
        chs = q.get("choices") or []
        if r["qtype"] == "객관식":
            if len(chs) != 5:
                warns.append(f"{where}: 객관식인데 선택지 {len(chs)}개")
            empty = [c["number"] for c in chs
                     if not "".join((b.get("value") or "") for b in c.get("contents") or []).strip()]
            if empty:
                errs.append(f"{where}: 빈 선택지 {empty}")
            # 정답이 선택지 범위 안인가
            a = (r["answer"] or "").strip()
            if a and a in CIRCLED and chs:
                idx = CIRCLED.index(a) + 1
                if idx > len(chs):
                    errs.append(f"{where}: 정답 {a} 가 선택지 수({len(chs)}) 초과")
        elif chs:
            warns.append(f"{where}: {r['qtype']}인데 선택지 {len(chs)}개")

        # LaTeX 균형
        for b in blocks_of(q):
            v = b.get("value") or ""
            if not latex_balanced(v):
                errs.append(f"{where}: LaTeX 불균형 — {v[:60]!r}")
                break
            if "[판독불가]" in v:
                warns.append(f"{where}: 판독불가 표기 있음")
                break

        # ⚠️ 부모 score 는 소문항 총점인 경우가 많다 — 둘 다 더하면 이중 계산된다.
        #    부모 배점이 있으면 그것만, 없으면 소문항 합을 쓴다.
        sc = q.get("score")
        subs = [s.get("score") for s in (q.get("sub_questions") or [])
                if isinstance(s.get("score"), (int, float))]
        if isinstance(sc, (int, float)):
            score_sum += sc
        elif subs:
            score_sum += sum(subs)

    return score_sum


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exam", type=int)
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    q = """SELECT e.id, e.school, e.grade, e.subject, e.year, e.semester, e.round
           FROM exams e WHERE e.ocr_status='done'"""
    if a.exam:
        q += f" AND e.id={a.exam}"
    exams = con.execute(q + " ORDER BY e.id").fetchall()

    errs, warns, scores = [], [], []
    for e in exams:
        tag = f"[{e['school']}][{e['grade']}][{e['subject']}][{e['year']%100}-{e['semester']}-{e['round']}]"
        rows = con.execute("""SELECT number, qtype, ocr_json, answer FROM questions
                              WHERE exam_id=? ORDER BY number""", (e["id"],)).fetchall()
        if not rows:
            errs.append(f"{tag}: ocr_status=done 인데 문항 0개")
            continue
        s = audit_exam(e["id"], e["school"], tag, rows, errs, warns)
        scores.append((tag, s, len(rows)))

    print(f"감사 대상 {len(exams)}편")
    print(f"\n오류 {len(errs)}건")
    for x in errs[:25]:
        print(f"  ✗ {x}")
    print(f"\n경고 {len(warns)}건")
    for x in warns[:20]:
        print(f"  ! {x}")

    print("\n--- 배점 합계 (100 근처가 정상, 학원 대비지는 다를 수 있음) ---")
    off = [(t, s, n) for t, s, n in scores if s and abs(s - 100) > 5]
    print(f"  100±5 벗어남: {len(off)}/{len(scores)}편")
    for t, s, n in off[:10]:
        print(f"    {t}  {s:.1f}점  ({n}문항)")

    # 정답 커버리지
    cov = con.execute("""SELECT COUNT(*), SUM(answer IS NOT NULL AND answer<>'')
                         FROM questions""").fetchone()
    print(f"\n정답 커버리지: {cov[1] or 0}/{cov[0]} ({(cov[1] or 0)/max(1,cov[0])*100:.1f}%)")
    con.close()

    bad = len(errs) + (len(warns) if a.strict else 0)
    print(f"\n{'FAIL' if bad else 'PASS'}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
