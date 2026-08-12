# -*- coding: utf-8 -*-
"""문제 DB 조회 — 저장된 데이터가 실제로 쓸 수 있는지 확인/활용용

  python db/query.py stats                     전체 통계
  python db/query.py find --grade 1 --subject 공수2
  python db/query.py find --text 무게중심       발문 검색
  python db/query.py show <question_id>        문항 원문
"""
from __future__ import annotations
import argparse, json, sqlite3, sys, io, pathlib

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
DB = pathlib.Path(__file__).with_name("exam_index.db")


def con():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def blocks_text(q: dict) -> str:
    out = []
    for b in q.get("contents") or []:
        v = b.get("value") or ""
        t = b.get("type")
        out.append(f"${v}$" if t and t.startswith("equation") else
                   (f"[그림]" if t == "figure" else v))
    return " ".join(out)


def cmd_stats(_):
    c = con()
    ex = c.execute("SELECT COUNT(*) n FROM exams WHERE ocr_status='done'").fetchone()["n"]
    qn = c.execute("SELECT COUNT(*) n FROM questions").fetchone()["n"]
    print(f"OCR 완료 시험지: {ex:,}편   적재 문항: {qn:,}개")
    print("\n--- 유형별 ---")
    for r in c.execute("SELECT qtype, COUNT(*) n FROM questions GROUP BY qtype ORDER BY n DESC"):
        print(f"  {r['qtype'] or '?':<8} {r['n']:,}")
    print("\n--- 학년·과목별 ---")
    for r in c.execute("""SELECT e.level, e.grade, e.subject, COUNT(q.id) n
                          FROM exams e JOIN questions q ON q.exam_id=e.id
                          GROUP BY e.level,e.grade,e.subject ORDER BY n DESC"""):
        print(f"  {r['level']}{r['grade']} {r['subject'] or '?':<8} {r['n']:,}")
    print("\n--- 정답/해설 보유 ---")
    a = c.execute("SELECT COUNT(*) n FROM questions WHERE answer IS NOT NULL AND answer<>''").fetchone()["n"]
    s = c.execute("SELECT COUNT(*) n FROM questions WHERE solution IS NOT NULL AND solution<>''").fetchone()["n"]
    print(f"  정답 {a:,} / 해설 {s:,}  (총 {qn:,})")
    c.close()


def cmd_find(a):
    c = con()
    sql = """SELECT q.id, e.school, e.grade, e.subject, e.year, e.semester, e.round,
                    q.number, q.qtype, q.ocr_json, q.answer
             FROM questions q JOIN exams e ON e.id=q.exam_id WHERE 1=1"""
    args = []
    if a.grade:   sql += " AND e.grade=?";   args.append(a.grade)
    if a.subject: sql += " AND e.subject=?"; args.append(a.subject)
    if a.year:    sql += " AND e.year=?";    args.append(a.year)
    if a.school:  sql += " AND e.school=?";  args.append(a.school)
    if a.text:    sql += " AND q.ocr_json LIKE ?"; args.append(f"%{a.text}%")
    sql += " ORDER BY e.year DESC, e.id, q.number LIMIT ?"
    args.append(a.limit)
    rows = c.execute(sql, args).fetchall()
    print(f"{len(rows)}건\n")
    for r in rows:
        q = json.loads(r["ocr_json"])
        head = f"[{r['school']}][{r['grade']}][{r['subject']}][{r['year']%100}-{r['semester']}-{r['round']}] #{r['number']}"
        print(f"  id={r['id']:<5} {head}  ({r['qtype']}, 정답 {r['answer'] or '-'})")
        print(f"        {blocks_text(q)[:110]}")
    c.close()


def cmd_show(a):
    c = con()
    r = c.execute("""SELECT q.*, e.school, e.grade, e.subject, e.year
                     FROM questions q JOIN exams e ON e.id=q.exam_id WHERE q.id=?""",
                  (a.qid,)).fetchone()
    if not r:
        sys.exit("없음")
    q = json.loads(r["ocr_json"])
    print(f"[{r['school']}][{r['grade']}][{r['subject']}][{r['year']}] #{r['number']}  {r['qtype']}")
    print(f"배점 {q.get('score')}  정답 {r['answer'] or '-'}  단원 {r['topic'] or '-'}  난이도 {r['difficulty'] or '-'}")
    print(f"\n{blocks_text(q)}")
    for ch in q.get("choices") or []:
        print(f"  ({ch['number']}) " + " ".join(
            (f"${b['value']}$" if b['type'].startswith('equation') else b['value'])
            for b in ch['contents']))
    for s in q.get("sub_questions") or []:
        print(f"  ({s['number']}) [{s.get('score')}점] " +
              " ".join(b.get('value', '') for b in s.get('contents', [])))
    if r["solution"]:
        print(f"\n[해설]\n{r['solution'][:600]}")
    c.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("stats").set_defaults(fn=cmd_stats)
    p = sub.add_parser("find")
    for f in ("subject", "school", "text"):
        p.add_argument(f"--{f}")
    p.add_argument("--grade", type=int); p.add_argument("--year", type=int)
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(fn=cmd_find)
    p = sub.add_parser("show"); p.add_argument("qid", type=int); p.set_defaults(fn=cmd_show)
    a = ap.parse_args()
    a.fn(a)
