# -*- coding: utf-8 -*-
"""<id>.answers.json → questions 테이블 정답·해설 병합

정답 추출 에이전트는 **본문을 건드리지 않고** 정답만 별도 파일로 낸다.
병합은 여기서 결정론적으로 한다(번호 매칭 + 정합성 검사).

  python db/merge_answers.py            전체
  python db/merge_answers.py --exam 4211
  python db/merge_answers.py --verify   완료본과 교차 대조(있는 편만)
"""
from __future__ import annotations
import argparse, json, re, sqlite3, sys, io, pathlib

BASE = pathlib.Path(__file__).parent
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
DB = BASE / "exam_index.db"
SRC = BASE / "ocr_pilot"
EXTRACTED = BASE / "extracted"

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"


def merge(path: pathlib.Path, con) -> tuple[int, int, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    eid = data.get("exam_id") or int(path.stem.split(".")[0])
    items = {int(i["number"]): i for i in data.get("items", []) if i.get("number")}
    rows = con.execute("SELECT id, number, qtype FROM questions WHERE exam_id=?",
                       (eid,)).fetchall()
    if not rows:
        return 0, 0, "본문 문항 없음(먼저 ingest 필요)"
    if not items:
        # 정답면이 인쇄돼 있지 않은 시험지(학교 원본 다수) — 결함이 아니다
        con.execute("UPDATE exams SET solution_status='no_source' WHERE id=?", (eid,))
        con.commit()
        return 0, 0, "정답면 없음(원본에 미인쇄)"

    cur = con.cursor()
    n_a = n_s = 0
    unmatched = []
    for qid, num, qtype in rows:
        it = items.get(num)
        if not it:
            unmatched.append(num)
            continue
        ans = (it.get("answer") or "").strip()
        sol = (it.get("solution") or "").strip()
        if ans == "[판독불가]":
            ans = ""
        # 객관식인데 원문자가 아니면 의심 — 기록만 하고 넣는다
        cur.execute("""UPDATE questions
                       SET answer=NULLIF(?,''), solution=NULLIF(?,''),
                           topic=COALESCE(NULLIF(?,''), topic),
                           difficulty=COALESCE(NULLIF(?,''), difficulty),
                           answer_source=CASE WHEN ?<>'' THEN 'printed' ELSE answer_source END
                       WHERE id=?""",
                    (ans, sol, (it.get("topic") or "").strip(),
                     (it.get("difficulty") or "").strip(), ans, qid))
        n_a += bool(ans)
        n_s += bool(sol)
    cur.execute("UPDATE exams SET solution_status=? WHERE id=?",
                ("done" if n_a else "pending", eid))
    con.commit()
    msg = f"매칭 {len(rows)-len(unmatched)}/{len(rows)}"
    if unmatched:
        msg += f"  미매칭 {unmatched[:8]}"
    return n_a, n_s, msg


def sanity(con) -> None:
    """객관식 정답이 원문자인지 등 기초 정합성."""
    bad = con.execute("""SELECT e.school, q.number, q.answer
        FROM questions q JOIN exams e ON e.id=q.exam_id
        WHERE q.qtype='객관식' AND q.answer IS NOT NULL
          AND q.answer NOT IN ('①','②','③','④','⑤')""").fetchall()
    print(f"\n객관식 정답 형식 이상: {len(bad)}건")
    for r in bad[:10]:
        print(f"    {r[0]} #{r[1]}: {r[2]!r}")

    dist = con.execute("""SELECT answer, COUNT(*) FROM questions
        WHERE qtype='객관식' AND answer IN ('①','②','③','④','⑤')
        GROUP BY answer ORDER BY answer""").fetchall()
    tot = sum(d[1] for d in dist)
    print(f"\n객관식 정답 분포 (총 {tot}):")
    for a, n in dist:
        print(f"    {a} {n:>4}  ({n/max(1,tot)*100:4.1f}%)")
    # 균등에서 크게 벗어나면 판독 편향 의심
    if tot >= 50:
        worst = max(abs(n / tot - 0.2) for _, n in dist)
        print(f"  균등(20%) 최대 편차 {worst*100:.1f}%p"
              f"{'  ← 편향 의심' if worst > 0.12 else '  (정상 범위)'}")


def verify_vs_ref(con) -> None:
    """완료본 추출본이 있는 편은 정답을 교차 대조."""
    print("\n=== 완료본 교차 대조 ===")
    tot = agree = 0
    for f in sorted(EXTRACTED.glob("*.json")):
        eid = int(f.stem)
        rows = con.execute("""SELECT number, answer FROM questions
                              WHERE exam_id=? AND answer IS NOT NULL""", (eid,)).fetchall()
        if not rows:
            continue
        ref = {q["number"]: (q.get("answer") or "") for q in
               json.loads(f.read_text(encoding="utf-8"))["questions"]}
        m = d = 0
        for num, ans in rows:
            r = ref.get(num)
            if not r or not ans:
                continue
            tot += 1
            if r.strip() == ans.strip():
                agree += 1; m += 1
            else:
                d += 1
                if d <= 3:
                    print(f"    exam {eid} #{num}: PDF={ans!r} vs 완료본={r!r}")
        if m or d:
            print(f"  exam {eid}: 일치 {m}, 불일치 {d}")
    if tot:
        print(f"  전체 일치율 {agree}/{tot} ({agree/tot*100:.1f}%)")
    else:
        print("  대조 가능한 편 없음")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exam", type=int)
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()

    con = sqlite3.connect(DB)
    con.execute("PRAGMA journal_mode=WAL")
    files = ([SRC / f"{a.exam}.answers.json"] if a.exam
             else sorted(SRC.glob("*.answers.json")))
    ta = ts = 0
    for f in files:
        if not f.exists():
            print(f"  없음: {f.name}"); continue
        n_a, n_s, msg = merge(f, con)
        ta += n_a; ts += n_s
        # 정답면이 없는 시험지는 결함이 아니라 '출처 없음' 상태다(FAIL 로 보이면 오해)
        mark = "OK  " if n_a else ("SKIP" if "없음" in msg else "FAIL")
        print(f"  {mark} {f.name:<24} 정답 {n_a:>3} 해설 {n_s:>3}  {msg}")
    print(f"\n병합 완료 — 정답 {ta}개 / 해설 {ts}개")
    sanity(con)
    if a.verify:
        verify_vs_ref(con)
    con.close()


if __name__ == "__main__":
    main()
