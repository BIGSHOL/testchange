# -*- coding: utf-8 -*-
"""born-digital PDF 텍스트 레이어 → 문항 골격 (OCR 전사량 절감)

이 코퍼스의 born-digital PDF 는 완료본을 내보낸 것이라 텍스트 레이어에
**한글 발문·문항 경계·선택지 마커·[소단원]·[난이도]** 가 그대로 들어 있다.
수식만 이미지라 빠지므로, 골격을 결정론적으로 뽑고 **수식 자리만 비워** 둔다.
그 빈칸만 비전으로 채우면 전사량이 크게 준다.

  python db/skeleton.py --exam 4211
"""
from __future__ import annotations
import argparse, json, re, sqlite3, sys, io, pathlib

BASE = pathlib.Path(__file__).parent
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import fitz

DB = BASE / "exam_index.db"
PAGES = BASE / "pages"

_QNUM = re.compile(r"^\s*(\d{1,2})\s*\.\s*(.*)$")
_CHOICE = re.compile(r"^\s*([①-⑩])\s*(.*)$")
_TOPIC = re.compile(r"\[소단원\]\s*(.*)")
_DIFF = re.compile(r"\[난이도\]\s*(\S+)")
_ESSAY = re.compile(r"\[\s*(서술형|서답형|단답형)\s*(\d*)\s*\]")


def parse_text(pages: list[str]) -> list[dict]:
    """텍스트 레이어 줄들을 문항 단위로 자른다."""
    qs: list[dict] = []
    cur: dict | None = None
    for txt in pages:
        for raw in txt.splitlines():
            line = raw.rstrip()
            if not line.strip():
                continue
            m = _QNUM.match(line)
            if m and 1 <= int(m.group(1)) <= 40:
                num = int(m.group(1))
                # 문항 번호는 문서 전체에서 **단조 증가**한다. 본문 속 "1." 오탐 차단.
                if num == (qs[-1]["number"] + 1 if qs else 1):
                    rest = m.group(2).strip()
                    cur = {"number": num, "lines": [rest] if rest else [],
                           "choices": [], "topic": None, "difficulty": None}
                    qs.append(cur)
                    continue
            if cur is None:
                continue
            mt = _TOPIC.search(line)
            if mt:
                cur["topic"] = mt.group(1).strip() or None
                continue
            md = _DIFF.search(line)
            if md:
                cur["difficulty"] = md.group(1).strip()
                continue
            mc = _CHOICE.match(line)
            if mc:
                cur["choices"].append(mc.group(2).strip())
                continue
            cur["lines"].append(line.strip())
    return qs


def to_skeleton(qs: list[dict], meta: dict) -> dict:
    out = []
    for q in qs:
        body = " ".join(x for x in q["lines"] if x).strip()
        body = re.sub(r"\s{2,}", " ", body)
        label = None
        me = _ESSAY.search(body)
        if me:
            label = me.group(0)
        out.append({
            "number": q["number"],
            "type": ("서술형" if label and "서술" in label
                     else "단답형" if label else
                     "객관식" if len(q["choices"]) >= 4 else "미정"),
            "label": label,
            "topic": q["topic"], "difficulty": q["difficulty"],
            # 수식이 빠진 한글 골격 — 비전으로 수식만 채운다
            "stem_text": body,
            "choice_count": len(q["choices"]),
            "choices_text": q["choices"],
            "contents": None,          # 채워야 할 자리
        })
    return {"meta": meta, "questions": out}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exam", type=int, required=True)
    a = ap.parse_args()

    con = sqlite3.connect(DB)
    row = con.execute("""SELECT school,grade,subject,year,semester,round,src_path
                         FROM exams WHERE id=?""", (a.exam,)).fetchone()
    con.close()
    if not row:
        sys.exit("없는 exam_id")
    src = (PAGES / str(a.exam) / "src.pdf")
    if not src.exists():
        src = pathlib.Path(row[6])

    doc = fitz.open(src)
    pages = [doc[i].get_text() for i in range(doc.page_count)]
    doc.close()
    chars = sum(len(p.strip()) for p in pages)
    if chars < 200:
        sys.exit(f"스캔본(텍스트 {chars}자) — 골격 추출 불가, 전량 비전 판독 필요")

    qs = parse_text(pages)
    meta = dict(exam_id=a.exam, school=row[0], grade=row[1], subject=row[2],
                year=row[3], semester=row[4], round=row[5], source="text-layer")
    sk = to_skeleton(qs, meta)

    out = PAGES / str(a.exam) / "skeleton.json"
    out.write_text(json.dumps(sk, ensure_ascii=False, indent=1), encoding="utf-8")

    n = len(sk["questions"])
    nt = sum(1 for q in sk["questions"] if q["topic"])
    nd = sum(1 for q in sk["questions"] if q["difficulty"])
    nc = sum(1 for q in sk["questions"] if q["choice_count"] >= 4)
    print(f"텍스트 {chars:,}자 → 문항 {n}개")
    print(f"  소단원 {nt}/{n}   난이도 {nd}/{n}   선택지 5개 {nc}/{n}")
    print(f"  saved: {out}")
    print("\n--- 골격 샘플 3 ---")
    for q in sk["questions"][:3]:
        print(f"\n  #{q['number']} ({q['type']}) 단원={q['topic']} 난이도={q['difficulty']}")
        print(f"    {q['stem_text'][:150]}")


if __name__ == "__main__":
    main()
