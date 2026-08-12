# -*- coding: utf-8 -*-
"""OCR JSON → questions 테이블 적재 (+ 파이프라인 통과 검증)

DB 는 나중에 그대로 쓰인다(검색·재출제·HWP 변환). 그래서 적재 전에
`parse_ocr_response`/`build_document` 를 태워 **변환 가능**함을 확인하고,
수식은 LaTeX 로 저장한다(웹 표시·검색 + 후일 HWP 변환 양쪽에 쓰인다).

  python db/ingest.py                 db/ocr_pilot/*.json 전부 적재
  python db/ingest.py --exam 4209     한 편만
  python db/ingest.py --check         적재 없이 검증만
"""
from __future__ import annotations
import argparse, json, sqlite3, sys, io, pathlib

BASE = pathlib.Path(__file__).parent
sys.path.insert(0, str(BASE.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from core.content_parser import parse_ocr_response, build_document
from core.latex_to_hwpeq import latex_to_hwpeq

DB = BASE / "exam_index.db"
SRC = BASE / "ocr_pilot"


def flatten(blocks) -> str:
    """블록 목록 → 검색용 평문(수식은 $...$ 로 감싼다)."""
    out = []
    for b in blocks or []:
        t = b.get("type")
        v = b.get("value") or ""
        if t == "text":
            out.append(v)
        elif t in ("equation", "equation_block"):
            out.append(f"${v}$")
        elif t == "figure":
            out.append(f"[그림: {v}]")
    return " ".join(out).strip()


def verify(data: dict) -> tuple[bool, str]:
    """파이프라인 통과 + 수식 누수 검사."""
    try:
        page = parse_ocr_response(data, 1)
        build_document([page], title=(data.get("header") or {}).get("title", ""))
    except Exception as ex:
        return False, f"parse/build 실패: {type(ex).__name__} {ex}"
    leak = 0
    for q in page.questions:
        blocks = list(q.contents)
        for ch in q.choices:
            blocks += list(ch.contents)
        for b in blocks:
            if b.type.name.startswith("EQUATION") and "\\" in latex_to_hwpeq(b.value):
                leak += 1
    return (leak == 0), (f"수식 누수 {leak}건" if leak else "OK")


def ingest(path: pathlib.Path, con, check_only: bool) -> tuple[int, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    eid = (data.get("meta") or {}).get("exam_id") or int(path.stem)
    ok, msg = verify(data)
    if not ok:
        return 0, msg
    qs = data.get("questions") or []
    if check_only:
        return len(qs), msg

    cur = con.cursor()
    cur.execute("DELETE FROM questions WHERE exam_id=?", (eid,))   # 재적재 멱등
    for q in qs:
        cur.execute("""INSERT INTO questions
            (exam_id, number, qtype, ocr_json, answer, solution, topic, difficulty)
            VALUES (?,?,?,?,?,?,?,?)""",
            (eid, q.get("number"), q.get("type"),
             json.dumps(q, ensure_ascii=False),
             q.get("answer"), q.get("solution"),
             q.get("topic"), q.get("difficulty")))
    cur.execute("""UPDATE exams SET ocr_status='done', question_count=? WHERE id=?""",
                (len(qs), eid))
    con.commit()
    return len(qs), msg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exam", type=int)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    # `<id>.answers.json` 은 정답 전용 파일 — merge_answers.py 담당이라 여기선 제외
    files = ([SRC / f"{a.exam}.json"] if a.exam else
             sorted(p for p in SRC.glob("*.json")
                    if not p.name.endswith(".answers.json")))
    con = sqlite3.connect(DB)
    con.execute("PRAGMA journal_mode=WAL")
    tot = 0
    for f in files:
        if not f.exists():
            print(f"  없음: {f}"); continue
        n, msg = ingest(f, con, a.check)
        tot += n
        mark = "OK  " if n else "FAIL"
        print(f"  {mark} {f.stem}  문항 {n:>3}  {msg}")
    con.close()
    print(f"\n{'검증' if a.check else '적재'} 완료 — 문항 {tot}개")


if __name__ == "__main__":
    main()
