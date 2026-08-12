# -*- coding: utf-8 -*-
"""[소단원]/[난이도] 백필 — PDF 텍스트 레이어의 숨김 메타데이터에서 결정론적 회수

born-digital 시험지에는 **흰 글자(#FFFFFF)로 인쇄 비표시 메타데이터**가 들어 있다
(완료본 규약). 화면엔 안 보이지만 텍스트 레이어에는 남아 있어 그대로 뽑을 수 있다.
비전 판독이 아니라 결정론적 추출이라 비용도 0이고 오독도 없다.

  python db/backfill_meta.py            메타 없는 편 전부
  python db/backfill_meta.py --exam 4294
  python db/backfill_meta.py --dry
"""
from __future__ import annotations
import argparse, json, re, sqlite3, sys, io, pathlib

BASE = pathlib.Path(__file__).parent
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import fitz

DB = BASE / "exam_index.db"
PAGES = BASE / "pages"

_QNUM = re.compile(r"^\s*(\d{1,2})\s*\.\s")
_TOPIC = re.compile(r"\[(?:소단원|중단원)\]\s*([^\[\]\n]*)")
_DIFF = re.compile(r"\[난이도\]\s*([^\s\[\]]+)")


def extract(pdf: pathlib.Path) -> dict[int, dict]:
    """문항번호 → {topic, difficulty}. 메타는 해당 문항 **뒤**에 붙어 있다."""
    doc = fitz.open(pdf)
    lines: list[str] = []
    for i in range(doc.page_count):
        lines += doc[i].get_text().splitlines()
    doc.close()

    out: dict[int, dict] = {}
    cur = None          # 현재 문항 번호(단조 증가로만 갱신 — 본문 속 "1." 오탐 차단)
    last = 0
    for ln in lines:
        m = _QNUM.match(ln)
        if m:
            n = int(m.group(1))
            if n == last + 1:
                cur, last = n, n
        if cur is None:
            continue
        mt = _TOPIC.search(ln)
        if mt and mt.group(1).strip():
            out.setdefault(cur, {})["topic"] = mt.group(1).strip()
        md = _DIFF.search(ln)
        if md:
            out.setdefault(cur, {})["difficulty"] = md.group(1).strip()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exam", type=int)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    con = sqlite3.connect(DB)
    con.execute("PRAGMA journal_mode=WAL")
    sql = """SELECT e.id, e.school, e.grade, e.subject, e.year, e.semester, e.round, e.src_path
             FROM exams e WHERE e.ocr_status='done'"""
    if a.exam:
        sql += f" AND e.id={a.exam}"
    exams = con.execute(sql + " ORDER BY e.id").fetchall()

    tot_t = tot_d = 0
    hit_exams = 0
    for eid, sch, gr, subj, yr, sem, rnd, src in exams:
        pdf = PAGES / str(eid) / "src.pdf"
        if not pdf.exists():
            pdf = pathlib.Path(src)
        if not pdf.exists():
            continue
        try:
            meta = extract(pdf)
        except Exception as ex:
            print(f"  ERR {eid}: {type(ex).__name__} {ex}")
            continue
        if not meta:
            continue
        nt = nd = 0
        cur = con.cursor()
        for num, m in meta.items():
            t, d = m.get("topic"), m.get("difficulty")
            if not t and not d:
                continue
            if not a.dry:
                cur.execute("""UPDATE questions
                               SET topic=COALESCE(NULLIF(topic,''), ?),
                                   difficulty=COALESCE(NULLIF(difficulty,''), ?)
                               WHERE exam_id=? AND number=?""", (t, d, eid, num))
                if cur.rowcount:
                    nt += bool(t); nd += bool(d)
            else:
                nt += bool(t); nd += bool(d)
        if nt or nd:
            hit_exams += 1
            tot_t += nt; tot_d += nd
            tag = f"[{sch}][{gr}][{subj}][{yr%100}-{sem}-{rnd}]"
            print(f"  {tag:<42} 소단원 {nt:>3}  난이도 {nd:>3}")
    if not a.dry:
        con.commit()

    print(f"\n{'[dry] ' if a.dry else ''}{hit_exams}편에서 소단원 {tot_t} / 난이도 {tot_d} 회수")
    r = con.execute("""SELECT COUNT(*),
                              SUM(topic IS NOT NULL AND topic<>''),
                              SUM(difficulty IS NOT NULL AND difficulty<>'')
                       FROM questions""").fetchone()
    print(f"전체 문항 {r[0]:,} 중 소단원 {r[1] or 0:,} ({(r[1] or 0)/r[0]*100:.1f}%)"
          f" / 난이도 {r[2] or 0:,} ({(r[2] or 0)/r[0]*100:.1f}%)")
    con.close()


if __name__ == "__main__":
    main()
