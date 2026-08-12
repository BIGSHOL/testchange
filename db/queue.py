# -*- coding: utf-8 -*-
"""OCR 작업 큐 — 중단·재개 지원 (PC 가 꺼져도 진행분 보존)

  python db/queue.py status                 진행 현황
  python db/queue.py next [--limit 5]       다음 작업 대상
  python db/queue.py done <exam_id>         완료 표시(산출 JSON 존재 확인)
  python db/queue.py scan                   db/ocr_pilot/*.json 스캔해 상태 일괄 동기화
"""
import argparse, json, sqlite3, sys, io, pathlib

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
DB = pathlib.Path(__file__).with_name("exam_index.db")
OUT = pathlib.Path(__file__).with_name("ocr_pilot")


def con():
    c = sqlite3.connect(DB)
    c.execute("PRAGMA journal_mode=WAL")      # 급정전 시 DB 손상 방지
    return c


def cmd_status(_):
    c = con()
    tot = c.execute("SELECT COUNT(*) FROM exams").fetchone()[0]
    print(f"전체 고유 시험지: {tot:,}")
    print("\n--- OCR 상태 ---")
    for st, n in c.execute("SELECT ocr_status, COUNT(*) FROM exams GROUP BY ocr_status"):
        print(f"  {st or 'pending':<10} {n:,}")
    print("\n--- 해설 상태 ---")
    for st, n in c.execute("SELECT solution_status, COUNT(*) FROM exams GROUP BY solution_status"):
        print(f"  {st or 'pending':<10} {n:,}")
    done = c.execute("SELECT COUNT(*) FROM exams WHERE ocr_status='done'").fetchone()[0]
    q = c.execute("SELECT SUM(question_count) FROM exams WHERE ocr_status='done'").fetchone()[0] or 0
    print(f"\n완료 {done:,}편 / 문항 {q:,}개  ({done/max(1,tot)*100:.2f}%)")
    c.close()


def cmd_next(a):
    c = con()
    rows = c.execute("""
      SELECT id, school, grade, subject, year, semester, round, src_path
      FROM exams WHERE ocr_status='pending' AND needs_pdf_convert=0
      ORDER BY year DESC, id LIMIT ?""", (a.limit,)).fetchall()
    for r in rows:
        print(f"{r[0]}\t[{r[1]}][{r[2]}][{r[3]}][{r[4]%100}-{r[5]}-{r[6]}]\t{r[7]}")
    c.close()


def cmd_done(a):
    f = OUT / f"{a.exam_id}.json"
    if not f.exists():
        sys.exit(f"산출 JSON 없음: {f}")
    d = json.loads(f.read_text(encoding="utf-8"))
    n = len(d.get("questions") or [])
    if not n:
        sys.exit("문항 0개 — 완료로 표시하지 않음")
    c = con()
    c.execute("UPDATE exams SET ocr_status='done', question_count=? WHERE id=?", (n, a.exam_id))
    c.commit(); c.close()
    print(f"exam {a.exam_id} → done ({n}문항)")


def cmd_scan(_):
    """산출물 기준으로 상태 재동기화 — 크래시 후 복구용."""
    c = con()
    ok = 0
    for f in sorted(OUT.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            print(f"  손상: {f.name}")       # 정전 중 쓰기 실패분
            continue
        qs = d.get("questions") or []
        if not qs:
            continue
        has_sol = all(q.get("solution") for q in qs)
        c.execute("UPDATE exams SET ocr_status='done', question_count=?, solution_status=? WHERE id=?",
                  (len(qs), 'done' if has_sol else 'pending', int(f.stem)))
        ok += 1
    c.commit(); c.close()
    print(f"동기화 {ok}편")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    p = sub.add_parser("next"); p.add_argument("--limit", type=int, default=5); p.set_defaults(fn=cmd_next)
    p = sub.add_parser("done"); p.add_argument("exam_id", type=int); p.set_defaults(fn=cmd_done)
    sub.add_parser("scan").set_defaults(fn=cmd_scan)
    a = ap.parse_args()
    a.fn(a)
