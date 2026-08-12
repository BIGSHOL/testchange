# -*- coding: utf-8 -*-
"""내용 기반 중복 시험지 검출

파일명 메타(학교·학년·과목·학기)로 중복을 걸렀지만, **라벨이 잘못 붙은 사본**은
빠져나간다(4324 vs 4325 실사례 — 같은 시험지인데 한쪽이 25-1-중간, 다른 쪽이
25-2-중간으로 카탈로그돼 별개로 적재됐다).

발문 텍스트 지문(fingerprint)으로 실제 내용이 같은 편을 찾는다.

  python db/dedup_content.py            검출만
  python db/dedup_content.py --apply    중복분을 duplicate_of 로 표시(삭제는 안 함)
"""
from __future__ import annotations
import argparse, hashlib, json, re, sqlite3, sys, io, pathlib, collections

BASE = pathlib.Path(__file__).parent
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
DB = BASE / "exam_index.db"


def norm(s: str) -> str:
    """비교용 — 공백·수식기호 차이를 지우고 한글/숫자/영문만 남긴다."""
    s = re.sub(r"[\s$\\{}^_~,.]+", "", s or "")
    return s.lower()


def fingerprint(con, eid: int) -> tuple[str, int]:
    rows = con.execute("""SELECT ocr_json FROM questions
                          WHERE exam_id=? ORDER BY number""", (eid,)).fetchall()
    parts = []
    for (js,) in rows:
        q = json.loads(js)
        t = "".join((b.get("value") or "") for b in (q.get("contents") or []))
        parts.append(norm(t)[:120])          # 문항별 앞부분만 — OCR 미세차 흡수
    body = "|".join(parts)
    return hashlib.sha1(body.encode("utf-8")).hexdigest(), len(rows)


def similarity(a: list[str], b: list[str]) -> float:
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    return len(sa & sb) / max(len(sa), len(sb))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--threshold", type=float, default=0.85)
    a = ap.parse_args()

    con = sqlite3.connect(DB)
    con.execute("PRAGMA journal_mode=WAL")
    cols = [r[1] for r in con.execute("PRAGMA table_info(exams)")]
    if "duplicate_of" not in cols:
        con.execute("ALTER TABLE exams ADD COLUMN duplicate_of INTEGER")
        con.commit()

    exams = con.execute("""SELECT e.id, e.school, e.grade, e.subject, e.year,
                                  e.semester, e.round
                           FROM exams e WHERE e.ocr_status='done'
                             AND e.duplicate_of IS NULL ORDER BY e.id""").fetchall()
    stems: dict[int, list[str]] = {}
    meta: dict[int, tuple] = {}
    for eid, *m in exams:
        rows = con.execute("""SELECT ocr_json FROM questions
                              WHERE exam_id=? ORDER BY number""", (eid,)).fetchall()
        st = []
        for (js,) in rows:
            q = json.loads(js)
            t = norm("".join((b.get("value") or "") for b in (q.get("contents") or [])))
            if len(t) >= 20:
                st.append(t[:120])
        if st:
            stems[eid] = st
            meta[eid] = tuple(m)

    ids = sorted(stems)
    dups = []
    for i, x in enumerate(ids):
        for y in ids[i + 1:]:
            # 문항 수가 많이 다르면 건너뛴다(빠른 배제)
            if abs(len(stems[x]) - len(stems[y])) > 3:
                continue
            s = similarity(stems[x], stems[y])
            if s >= a.threshold:
                dups.append((x, y, s))

    print(f"검사 {len(ids)}편 → 중복 후보 {len(dups)}쌍 (임계 {a.threshold})")
    for x, y, s in dups:
        mx, my = meta[x], meta[y]
        print(f"\n  유사도 {s:.0%}")
        print(f"    {x}: [{mx[0]}][{mx[1]}][{mx[2]}][{mx[3]%100}-{mx[4]}-{mx[5]}]  {len(stems[x])}문항")
        print(f"    {y}: [{my[0]}][{my[1]}][{my[2]}][{my[3]%100}-{my[4]}-{my[5]}]  {len(stems[y])}문항")
        if a.apply:
            keep, drop = (x, y) if len(stems[x]) >= len(stems[y]) else (y, x)
            con.execute("UPDATE exams SET duplicate_of=? WHERE id=?", (keep, drop))
            print(f"    → {drop} 를 {keep} 의 중복으로 표시(데이터는 보존)")
    if a.apply:
        con.commit()
        n = con.execute("SELECT COUNT(*) FROM exams WHERE duplicate_of IS NOT NULL").fetchone()[0]
        print(f"\n중복 표시 누계 {n}편 — 조회·내보내기에서 제외하려면 duplicate_of IS NULL 조건 사용")
    con.close()


if __name__ == "__main__":
    main()
