# -*- coding: utf-8 -*-
"""완료본의 정답·해설·소단원·난이도를 문제 DB 에 채운다.

문제 본문은 OCR 산출물을 쓰고, **정답/해설/메타만** 완료본(사람 검수본)에서 가져온다.
완료본 수식은 HWP 스크립트이므로 `hwpeq_to_latex` 로 LaTeX 로 바꿔 DB 표기를 통일한다.

  python db/fill_answers.py --exam 4209
  python db/fill_answers.py --all            OCR 완료된 편 전부
"""
from __future__ import annotations
import argparse, json, re, sqlite3, sys, io, pathlib, tempfile, shutil

BASE = pathlib.Path(__file__).parent
sys.path.insert(0, str(BASE.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from core.hwpeq_to_latex import hwpeq_to_latex

DB = BASE / "exam_index.db"
EXTRACTED = BASE / "extracted"


def to_latex(s: str | None) -> str | None:
    """``$HWP스크립트$`` 조각을 LaTeX 로 치환."""
    if not s:
        return s
    return re.sub(r"\$([^$]+)\$", lambda m: f"${hwpeq_to_latex(m.group(1))}$", s)


def source_json(eid: int, con) -> pathlib.Path | None:
    """완료본 추출 JSON. 없으면 hwp_extract 로 즉시 생성."""
    p = EXTRACTED / f"{eid}.json"
    if p.exists():
        return p
    row = con.execute("""
        SELECT path FROM exam_files
        WHERE exam_id=? AND ext IN ('.hwp','.hwpx')
          AND (status LIKE '%완료%' OR path LIKE '%워드%')
        ORDER BY (status LIKE '%완료%') DESC LIMIT 1""", (eid,)).fetchone()
    if not row:
        return None
    from scripts.hwp_extract import to_hwpx, parse_exam
    work = pathlib.Path(tempfile.mkdtemp(prefix="fill_"))
    try:
        data = parse_exam(to_hwpx(pathlib.Path(row[0]), work))
        EXTRACTED.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        return p
    except Exception as ex:
        print(f"    완료본 추출 실패: {type(ex).__name__} {ex}")
        return None
    finally:
        shutil.rmtree(work, ignore_errors=True)


def fill(eid: int, con) -> tuple[int, int, str]:
    src = source_json(eid, con)
    if not src:
        return 0, 0, "완료본 없음"
    ref = {q["number"]: q for q in json.loads(src.read_text(encoding="utf-8"))["questions"]}
    rows = con.execute("SELECT id, number FROM questions WHERE exam_id=? ORDER BY number",
                       (eid,)).fetchall()
    if not rows:
        return 0, 0, "OCR 문항 없음"

    n_ans = n_sol = 0
    cur = con.cursor()
    for qid, num in rows:
        r = ref.get(num)
        if not r:
            continue
        ans = to_latex(r.get("answer"))
        sol = to_latex(r.get("solution"))
        cur.execute("""UPDATE questions
                       SET answer=COALESCE(NULLIF(?,''), answer),
                           solution=COALESCE(NULLIF(?,''), solution),
                           topic=COALESCE(NULLIF(?,''), topic),
                           difficulty=COALESCE(NULLIF(?,''), difficulty)
                       WHERE id=?""",
                    (ans, sol, r.get("topic"), r.get("difficulty"), qid))
        n_ans += bool(ans)
        n_sol += bool(sol)
    cur.execute("UPDATE exams SET solution_status=? WHERE id=?",
                ("done" if n_ans else "pending", eid))
    con.commit()
    matched = len(set(ref) & {n for _, n in rows})
    return n_ans, n_sol, f"문항매칭 {matched}/{len(rows)} (완료본 {len(ref)}문항)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exam", type=int)
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()

    con = sqlite3.connect(DB)
    con.execute("PRAGMA journal_mode=WAL")
    if a.exam:
        ids = [a.exam]
    else:
        ids = [r[0] for r in con.execute(
            "SELECT id FROM exams WHERE ocr_status='done' ORDER BY id")]
    for eid in ids:
        n_ans, n_sol, msg = fill(eid, con)
        mark = "OK  " if n_ans else "SKIP"
        print(f"  {mark} exam {eid}  정답 {n_ans:>3}  해설 {n_sol:>3}  {msg}")
    con.close()


if __name__ == "__main__":
    main()
