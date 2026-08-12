# -*- coding: utf-8 -*-
"""정답 결측 문항을 풀이용으로 내보낸다 (db/solve/<exam_id>.questions.json)

정답면도 완료본도 없는 시험지가 있다. 그 문항은 직접 풀어 채우되,
**출처를 'computed' 로 구분**해 인쇄 정답(printed)과 섞이지 않게 한다.

  python db/solve_export.py            결측 있는 전체
  python db/solve_export.py --exam 4220
"""
from __future__ import annotations
import argparse, json, re, sqlite3, sys, io, pathlib

BASE = pathlib.Path(__file__).parent
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
DB = BASE / "exam_index.db"
OUT = BASE / "solve"


def render(q: dict) -> dict:
    def txt(blocks):
        out = []
        for b in blocks or []:
            t, v = (b.get("type") or ""), (b.get("value") or "")
            if t == "figure":
                out.append(f"[그림] {v}")
            elif t == "table":
                # ⚠️ table 은 value 가 아니라 rows 에 내용이 있다. 안 펼치면 표가
                #    통째로 사라져 문항을 풀 수 없다(구산고 #9 에서 발각).
                rows = b.get("rows") or []
                body = " / ".join(" | ".join(str(c) for c in r) for r in rows)
                out.append(f"[표] {body}" if body else (v or "[표]"))
            else:
                out.append(v)
        return " ".join(x for x in out if x).strip()

    return {
        "number": q.get("number"),
        "type": q.get("type"),
        "score": q.get("score"),
        "stem": txt(q.get("contents")),
        "choices": [{"number": c.get("number"), "text": txt(c.get("contents"))}
                    for c in (q.get("choices") or [])],
        "sub_questions": [{"number": s.get("number"), "score": s.get("score"),
                           "text": txt(s.get("contents"))}
                          for s in (q.get("sub_questions") or [])],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exam", type=int)
    a = ap.parse_args()

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    sql = """SELECT e.id, e.school, e.grade, e.subject, e.year, e.semester, e.round
             FROM exams e WHERE EXISTS (
               SELECT 1 FROM questions q WHERE q.exam_id=e.id
                 AND (q.answer IS NULL OR q.answer=''))"""
    if a.exam:
        sql += f" AND e.id={a.exam}"
    exams = con.execute(sql + " ORDER BY e.id").fetchall()

    OUT.mkdir(parents=True, exist_ok=True)
    total = 0
    manifest = []
    for e in exams:
        rows = con.execute("""SELECT number, ocr_json FROM questions
                              WHERE exam_id=? AND (answer IS NULL OR answer='')
                              ORDER BY number""", (e["id"],)).fetchall()
        qs = [render(json.loads(r["ocr_json"])) for r in rows]
        tag = (f"[{e['school']}][{e['grade']}][{e['subject']}]"
               f"[{e['year']%100}-{e['semester']}-{e['round']}]")
        p = OUT / f"{e['id']}.questions.json"
        p.write_text(json.dumps(
            {"exam_id": e["id"], "tag": tag, "count": len(qs), "questions": qs},
            ensure_ascii=False, indent=1), encoding="utf-8")
        total += len(qs)
        manifest.append({"id": e["id"], "tag": tag, "count": len(qs)})
        print(f"  {e['id']} {tag}  {len(qs)}문항 → {p.name}")
    con.close()

    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    print(f"\n총 {total}문항 / {len(exams)}편")
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
