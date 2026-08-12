# -*- coding: utf-8 -*-
"""OCR 대상 페이지 렌더 — 큐에서 pending 을 꺼내 판독용 PNG 생성

  python db/prep_pages.py --limit 3          다음 3편 준비
  python db/prep_pages.py --exam 4484        특정 편 준비

산출: db/pages/<exam_id>/p{n}.png  (+ meta.json)
PNG 는 재생성 가능하므로 git 추적 대상이 아니다.
"""
from __future__ import annotations
import argparse, json, shutil, sqlite3, sys, io, pathlib

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import fitz
from PIL import Image

BASE = pathlib.Path(__file__).parent
DB = BASE / "exam_index.db"
PAGES = BASE / "pages"
MAXW = 1100          # 판독용 폭 — 파일럿에서 이 크기로 전 페이지 정확 판독 확인


def prep(row) -> dict | None:
    eid, sch, gr, subj, yr, sem, rnd, src = row
    tag = f"[{sch}][{gr}][{subj}][{yr % 100}-{sem}-{rnd}]"
    out = PAGES / str(eid)
    out.mkdir(parents=True, exist_ok=True)
    try:
        local = out / "src.pdf"
        if not local.exists():
            shutil.copy2(src, local)          # 네트워크 드라이브 재읽기 방지
        doc = fitz.open(local)
    except Exception as ex:
        print(f"  FAIL {tag} :: {ex}")
        return None

    n = doc.page_count
    txt = sum(len(doc[i].get_text().strip()) for i in range(min(3, n)))
    born = txt > 200
    for i in range(n):
        p = out / f"p{i+1}.png"
        if p.exists():
            continue
        pix = doc[i].get_pixmap(dpi=150)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        if img.width > MAXW:
            img = img.resize((MAXW, int(img.height * MAXW / img.width)), Image.LANCZOS)
        img.save(p)
    doc.close()

    meta = dict(exam_id=eid, school=sch, grade=gr, subject=subj, year=yr,
                semester=sem, round=rnd, src=src, pages=n,
                born_digital=born, scan=not born)
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
    kind = "born-digital" if born else "스캔본"
    print(f"  OK  {tag}  {n}쪽  {kind}  → db/pages/{eid}/")
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=3)
    ap.add_argument("--exam", type=int)
    ap.add_argument("--with-ref", action="store_true",
                    help="완료본(정답·해설 보유)이 있는 시험지만 — 우선 처리 대상")
    a = ap.parse_args()

    con = sqlite3.connect(DB)
    con.execute("PRAGMA journal_mode=WAL")
    if a.exam:
        rows = con.execute("""SELECT id,school,grade,subject,year,semester,round,src_path
                              FROM exams WHERE id=?""", (a.exam,)).fetchall()
    else:
        ref = ("""AND id IN (SELECT exam_id FROM exam_files
                    WHERE ext IN ('.hwp','.hwpx')
                      AND (status LIKE '%완료%' OR path LIKE '%워드%'))"""
               if a.with_ref else "")
        rows = con.execute(f"""
          SELECT id,school,grade,subject,year,semester,round,src_path
          FROM exams WHERE ocr_status='pending' AND src_ext='.pdf' {ref}
          ORDER BY year DESC, id LIMIT ?""", (a.limit,)).fetchall()
    con.close()

    print(f"준비 대상 {len(rows)}편")
    for r in rows:
        prep(r)
    print(f"\n페이지 디렉터리: {PAGES}")


if __name__ == "__main__":
    main()
