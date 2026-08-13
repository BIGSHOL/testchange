# -*- coding: utf-8 -*-
"""워크플로 인자(JSON) 생성 — 페이지 준비된 pending 시험지 목록

  python db/batch_args.py --limit 12
  python db/batch_args.py --limit 12 --year-min 2024      2024~2025 만
  python db/batch_args.py --answers                       정답 추출용(문항수 포함)
"""
from __future__ import annotations
import argparse, json, sqlite3, sys, io, pathlib

import scope as _scope  # noqa: E402  (같은 폴더)

BASE = pathlib.Path(__file__).parent
# ⚠️ append 로 붙인다 — insert(0) 이면 db/ 안 모듈이 **표준 라이브러리를
#    가린다**(db/queue.py 가 queue 를 가려 requests 임포트가 죽었다).
sys.path.append(str(BASE))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
DB = BASE / "exam_index.db"
PAGES = BASE / "pages"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument("--year-min", type=int, default=2024)
    ap.add_argument("--level", choices=["중", "고"])
    ap.add_argument("--grade", type=int)
    ap.add_argument("--answers", action="store_true",
                    help="정답 추출용 — OCR 끝났는데 정답 없는 편")
    a = ap.parse_args()

    con = sqlite3.connect(DB)
    lv = f" AND e.level='{a.level}'" if a.level else ""
    gd = f" AND e.grade={a.grade}" if a.grade else ""
    if a.answers:
        rows = con.execute("""
          SELECT e.id, e.school, e.grade, e.subject, e.year, e.semester, e.round,
                 e.question_count
          FROM exams e
          WHERE e.ocr_status='done' AND e.solution_status='pending'
            AND e.year>=? AND {SCOPE}
          ORDER BY e.id LIMIT ?""".format(SCOPE=_scope.sql("e")), (a.year_min, a.limit)).fetchall()
    else:
        rows = con.execute("""
          SELECT e.id, e.school, e.grade, e.subject, e.year, e.semester, e.round, 0
          FROM exams e
          WHERE e.ocr_status='pending' AND e.src_ext='.pdf'
            AND e.year>=? AND {SCOPE} {LV} {GD}
          ORDER BY e.year DESC, e.id LIMIT ?""".format(SCOPE=_scope.sql("e"), LV=lv, GD=gd), (a.year_min, a.limit * 3)).fetchall()
    con.close()

    out = []
    for eid, sch, gr, subj, yr, sem, rnd, qc in rows:
        d = PAGES / str(eid)
        pngs = sorted(d.glob("p*.png")) if d.is_dir() else []
        if not pngs:
            continue                      # 페이지 미준비 — prep_pages 먼저
        item = {"id": eid,
                "tag": f"[{sch}][{gr}][{subj}][{yr % 100}-{sem}-{rnd}]",
                "pages": len(pngs)}
        if a.answers:
            item["qcount"] = qc
        out.append(item)
        if len(out) >= a.limit:
            break

    print(json.dumps(out, ensure_ascii=False))
    print(f"\n// {len(out)}편", file=sys.stderr)


if __name__ == "__main__":
    main()
