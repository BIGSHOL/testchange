# -*- coding: utf-8 -*-
"""독립 2회 풀이(A·B) 교차 대조 → 일치분만 정답으로 채운다

수학 정답은 하나만 틀려도 DB 신뢰도가 깨진다. 그래서 서로 모른 채 푼 두 결과가
**일치할 때만** 채우고, 갈리면 비워 둔 채 기록한다(추측 금지).
채운 값은 answer_source='computed' 로 표시해 인쇄 정답(printed)과 구분한다.

  python db/solve_merge.py            전체
  python db/solve_merge.py --dry      기입 없이 대조만
"""
from __future__ import annotations
import argparse, json, re, sqlite3, sys, io, pathlib, collections

BASE = pathlib.Path(__file__).parent
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
DB = BASE / "exam_index.db"
SOLVE = BASE / "solve"
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"


# 같은 뜻 다른 표기 — 값이 같은데 불일치로 잡히면 정답을 버리게 된다
_SYN = [(r"\\leq?\b", r"\\leq"), (r"\\geq?\b", r"\\geq"), (r"\\neq?\b", r"\\neq"),
        (r"\\cdot", r"\\times"), (r"\\dfrac", r"\\frac")]


def norm(s: str | None) -> str:
    """비교용 정규화 — 공백·달러·동의어·군더더기 표기를 흡수하되 값 자체는 보존."""
    s = (s or "").strip()
    s = s.replace("$", "").replace("\\,", "").replace("~", "").replace("\\ ", "")
    for pat, rep in _SYN:
        s = re.sub(pat, rep, s)
    s = re.sub(r"\s+", "", s)
    # ``x^{2}`` ≡ ``x^2`` — 한 글자 첨자의 중괄호는 LaTeX 상 의미가 같다.
    s = re.sub(r"([\^_])\{([^{}])\}", r"\1\2", s)
    # 한쪽만 붙이는 부연 ``(즉 a=6, b=-1)`` ``(직선 y=2x-3)`` 은 값이 아니다.
    s = re.sub(r"\((?:즉|따라서|직선|즉,)[^()]*\)$", "", s)
    return s


def value_of(s: str | None) -> str:
    """최종 값만 뽑는다.

    ``P(2)=6`` 과 ``6``, ``f(x)=(x+1)^2+4=x^2+2x+5`` 와 ``f(x)=x^2+2x+5`` 는
    같은 답인데 문자열이 다르다. 부등식(<,>,≤,≥)이 없고 등호가 있으면
    **마지막 등호 우변**이 최종 값이다.
    """
    n = norm(s)
    if not n:
        return ""
    if re.search(r"[<>]|\\leq|\\geq", n):
        return n                      # 부등식은 통째가 답(범위)
    if "=" in n:
        tail = n.rsplit("=", 1)[-1]
        if tail:
            return tail
    return n


def load(eid: int, p: str) -> dict[int, dict]:
    f = SOLVE / f"{eid}.{p}.json"
    if not f.exists():
        return {}
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception as ex:
        print(f"    {f.name} 파싱 실패: {ex}")
        return {}
    return {int(i["number"]): i for i in d.get("items", []) if i.get("number")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    con = sqlite3.connect(DB)
    con.execute("PRAGMA journal_mode=WAL")
    manifest = json.loads((SOLVE / "manifest.json").read_text(encoding="utf-8"))

    tot_agree = tot_disagree = tot_blank = 0
    disagreements = []
    for m in manifest:
        eid, tag = m["id"], m["tag"]
        A, B = load(eid, "A"), load(eid, "B")
        if not A or not B:
            print(f"  SKIP {tag}  (A={len(A)} B={len(B)})")
            continue
        rows = con.execute("""SELECT id, number, qtype FROM questions
                              WHERE exam_id=? AND (answer IS NULL OR answer='')
                              ORDER BY number""", (eid,)).fetchall()
        agree = dis = blank = 0
        cur = con.cursor()
        for qid, num, qtype in rows:
            ia, ib = A.get(num), B.get(num)
            aa = (ia or {}).get("answer") or ""
            ab = (ib or {}).get("answer") or ""
            if not aa or not ab:
                blank += 1
                continue
            # 증명형 서술("~임을 보여라")은 최종답이 없다. 긴 서술을 answer 에 넣으면
            # 비교가 무의미하므로 풀이로만 남기고 정답은 비운다.
            if qtype != "객관식" and (len(norm(aa)) > 60 or len(norm(ab)) > 60):
                blank += 1
                if not a.dry:
                    sol = (ia.get("solution") or "") or aa
                    cur.execute("""UPDATE questions
                                   SET solution=COALESCE(NULLIF(?,''), solution)
                                   WHERE id=?""", (sol, qid))
                continue
            if norm(aa) != norm(ab) and value_of(aa) != value_of(ab):
                dis += 1
                disagreements.append((tag, num, aa[:40], ab[:40]))
                continue
            # 객관식이면 원문자여야 한다(형식 게이트)
            if qtype == "객관식" and (len(aa.strip()) != 1 or aa.strip() not in CIRCLED):
                dis += 1
                disagreements.append((tag, num, f"형식이상:{aa[:30]}", ab[:30]))
                continue
            agree += 1
            if a.dry:
                continue
            sol = (ia.get("solution") or "") or (ib.get("solution") or "")
            conf = {"high": 0, "medium": 1, "low": 2}
            worst = max((ia.get("confidence") or "medium", ib.get("confidence") or "medium"),
                        key=lambda c: conf.get(c, 1))
            cur.execute("""UPDATE questions
                           SET answer=?, solution=COALESCE(NULLIF(?,''), solution),
                               answer_source=?
                           WHERE id=?""",
                        (aa.strip(), sol, f"computed:{worst}", qid))
        if not a.dry:
            con.commit()
            if agree:
                con.execute("UPDATE exams SET solution_status='computed' WHERE id=?", (eid,))
                con.commit()
        tot_agree += agree; tot_disagree += dis; tot_blank += blank
        rate = agree / max(1, len(rows)) * 100
        print(f"  {tag:<42} 일치 {agree:>3}/{len(rows):<3} ({rate:5.1f}%)  불일치 {dis}  미풀이 {blank}")

    print(f"\n{'[dry] ' if a.dry else ''}합계 — 일치 {tot_agree} / 불일치 {tot_disagree} / 미풀이 {tot_blank}")
    if disagreements:
        print("\n=== 불일치 (정답 미기입, 수동 확인 필요) ===")
        for tag, num, x, y in disagreements[:25]:
            print(f"  {tag} #{num}:  A={x!r}  B={y!r}")

    r = con.execute("""SELECT COALESCE(answer_source,'(없음)') s, COUNT(*)
                       FROM questions GROUP BY s ORDER BY 2 DESC""").fetchall()
    print("\n=== 정답 출처 분포 ===")
    for s, n in r:
        print(f"  {s:<18} {n:,}")
    con.close()


if __name__ == "__main__":
    main()
