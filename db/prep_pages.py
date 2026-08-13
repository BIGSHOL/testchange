# -*- coding: utf-8 -*-
"""OCR 대상 페이지 렌더 — 큐에서 pending 을 꺼내 판독용 PNG 생성

  python db/prep_pages.py --limit 3          다음 3편 준비
  python db/prep_pages.py --exam 4484        특정 편 준비

산출: db/pages/<exam_id>/p{n}.png  (+ meta.json)
PNG 는 재생성 가능하므로 git 추적 대상이 아니다.
"""
from __future__ import annotations
import argparse, json, os, shutil, sqlite3, sys, io, pathlib

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import fitz
from PIL import Image

BASE = pathlib.Path(__file__).parent
sys.path.insert(0, str(BASE))
import scope as _scope
DB = BASE / "exam_index.db"
PAGES = BASE / "pages"
MAXW = 1100          # 판독용 폭 — 파일럿에서 이 크기로 전 페이지 정확 판독 확인


def resolve_src(src: str) -> str | None:
    """원본 PDF 경로 해석 — N: 가 끊기면 로컬 미러 D:\\기출 로 폴백한다.

    N: 은 비영구 네트워크 매핑이라 세션 중 사라진다(실제로 작업 중 끊겼다).
    D:\\기출 이 같은 트리를 담고 있어 접두사만 바꾸면 그대로 이어진다.
    """
    if os.path.exists(src):
        return src
    for old, new in ((r"N:\개인\기출", r"D:\기출"),):
        if src.startswith(old):
            alt = new + src[len(old):]
            if os.path.exists(alt):
                return alt
    return None


def prep(row, pdf_only: bool = False) -> dict | None:
    """PNG 렌더는 **비전 판독용**이다. 텍스트 레이어 경로는 src.pdf 만 있으면
    되므로 pdf_only 로 복사만 하고 끝낸다(수백 편이면 렌더 시간·디스크가 크다).
    """
    eid, sch, gr, subj, yr, sem, rnd, src = row
    tag = f"[{sch}][{gr}][{subj}][{yr % 100}-{sem}-{rnd}]"
    out = PAGES / str(eid)
    out.mkdir(parents=True, exist_ok=True)
    try:
        local = out / "src.pdf"
        if not local.exists():
            real = resolve_src(src)
            if real is None:
                print(f"  MISS {tag} :: 원본 없음(N: 끊김 + 미러에도 없음)")
                return None
            shutil.copy2(real, local)         # 네트워크/미러 재읽기 방지
        doc = fitz.open(local)
    except Exception as ex:
        print(f"  FAIL {tag} :: {ex}")
        return None

    n = doc.page_count
    if pdf_only:
        doc.close()
        print(f"  PDF {tag}  {n}쪽 → db/pages/{eid}/src.pdf")
        return {"exam_id": eid, "pages": n}
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
    ap.add_argument("--pdf-only", action="store_true",
                    help="PNG 렌더 없이 원본 PDF 만 확보(텍스트 레이어 경로용)")
    ap.add_argument("--level", choices=["중", "고"], help="학교급 지정(균형 배분용)")
    ap.add_argument("--grade", type=int, help="학년 지정")
    ap.add_argument("--with-ref", action="store_true",
                    help="완료본(정답·해설 보유)이 있는 시험지만 — 우선 처리 대상")
    a = ap.parse_args()

    con = sqlite3.connect(DB)
    con.execute("PRAGMA journal_mode=WAL")
    if a.exam:
        rows = con.execute("""SELECT id,school,grade,subject,year,semester,round,src_path
                              FROM exams WHERE id=?""", (a.exam,)).fetchall()
    else:
        lv = f" AND level='{a.level}'" if a.level else ""
        gd = f" AND grade={a.grade}" if a.grade else ""
        ref = ("""AND id IN (SELECT exam_id FROM exam_files
                    WHERE ext IN ('.hwp','.hwpx')
                      AND (status LIKE '%완료%' OR path LIKE '%워드%'))"""
               if a.with_ref else "")
        rows = con.execute(f"""
          SELECT id,school,grade,subject,year,semester,round,src_path
          FROM exams WHERE ocr_status='pending' AND src_ext='.pdf'
            AND {_scope.sql()} {lv} {gd} {ref}
          ORDER BY year DESC, id LIMIT ?""", (a.limit,)).fetchall()
    con.close()

    print(f"준비 대상 {len(rows)}편")
    for r in rows:
        prep(r, a.pdf_only)
    print(f"\n페이지 디렉터리: {PAGES}")


if __name__ == "__main__":
    main()
