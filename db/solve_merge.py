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


_PART = re.compile(r"^\(\d{1,2}\)$")          # 소문항 라벨 (1)(2)(3) — 인수가 아니다


def _groups(s: str, i: int) -> tuple[list[str], int]:
    """위치 i 에서 시작하는 **연속 괄호 그룹**을 통째로 읽는다(중첩 대응)."""
    out = []
    while i < len(s) and s[i] == "(":
        depth, j = 0, i
        while j < len(s):
            if s[j] == "(":
                depth += 1
            elif s[j] == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if depth:                              # 괄호 불균형 — 건드리지 않는다
            return out, i
        out.append(s[i:j + 1])
        i = j + 1
    return out, i


def _sort_factors(s: str) -> str:
    """붙어 있는 괄호 인수를 사전순 정렬 — 곱셈은 교환법칙이 성립한다.

    ``(x^2+2x+3)(x^2-2x+3)`` 과 순서를 뒤집은 것은 **같은 답**인데 문자열이 달라
    불일치로 잡혔다(달서고 #20). 소문항 라벨 ``(1)(2)`` 는 순서가 뜻을 가지므로
    정렬 대상에서 제외한다.
    """
    out, i = [], 0
    while i < len(s):
        if s[i] == "(":
            grp, ni = _groups(s, i)
            if ni == i:                        # 불균형 — 원문 유지
                out.append(s[i]); i += 1; continue
            # 소문항 라벨을 경계로 잘라 **구간 안에서만** 정렬한다. 라벨은 순서가
            # 뜻을 가지므로 자리를 지키고, 한 구간 안 인수끼리만 교환법칙을 쓴다.
            seg, res = [], []
            for g in grp + [None]:
                if g is None or _PART.match(g):
                    res += sorted(seg) if len(seg) > 1 else seg
                    seg = []
                    if g is not None:
                        res.append(g)
                else:
                    seg.append(g)
            out.append("".join(res)); i = ni
        else:
            out.append(s[i]); i += 1
    return "".join(out)


_EQUIV = re.compile(r"^(.*?)\((?:즉|곧|즉,)(.+)\)$")


def _strip_point_label(s: str) -> str:
    """``P(-\\sqrt3,-1)`` ≡ ``(-\\sqrt3,-1)`` — 점 이름은 라벨이지 답이 아니다.

    쉼표가 든 괄호(좌표쌍) 앞의 홑 대문자만 뗀다. ``f(x)``(소문자)·``P(A∩B)``
    (쉼표 없음)는 대상이 아니다.
    """
    return re.sub(r"(?:\\mathrm\{([A-Z])\}|\b([A-Z]))(?=\([^()]*,[^()]*\))", "", s)


def norm(s: str | None) -> str:
    """비교용 정규화 — 공백·달러·동의어·군더더기 표기를 흡수하되 값 자체는 보존."""
    s = (s or "").strip()
    s = s.replace("$", "").replace("\\,", "").replace("~", "").replace("\\ ", "")
    for pat, rep in _SYN:
        s = re.sub(pat, rep, s)
    s = re.sub(r"\s+", "", s)
    # ``x^{2}`` ≡ ``x^2`` — 한 글자 첨자의 중괄호는 LaTeX 상 의미가 같다.
    s = re.sub(r"([\^_])\{([^{}])\}", r"\1\2", s)
    s = _strip_point_label(s)
    # 한쪽만 붙이는 부연 ``(즉 a=6, b=-1)`` ``(직선 y=2x-3)`` 은 값이 아니다.
    s = re.sub(r"\((?:즉|따라서|직선|즉,)[^()]*\)$", "", s)
    return _sort_factors(s)


def equiv_set(s: str | None) -> set[str]:
    """``X (즉 Y)`` 가 내놓는 **동치 표기 전부**를 모은다.

    쓰는 사람이 ``표준형 (즉 일반형)`` 이라고 적으면 둘이 같은 답이라는 선언이다.
    A 는 표준형을, B 는 일반형을 앞세우면 문자열은 달라도 답은 같다(대구고 #22).
    ⚠️ norm() 의 '부연 떼기'만으로는 **양쪽 다 부연을 단** 이 경우를 못 잡고,
    반대로 이 집합만 쓰면 **한쪽만 부연을 단** 경우를 놓친다 — 둘 다 필요하다.
    """
    raw = (s or "").strip().replace("$", "")
    m = _EQUIV.search(re.sub(r"\s+", " ", raw))
    parts = [m.group(1), m.group(2)] if m else [raw]
    return {norm(p) for p in parts if norm(p)}


def same_answer(a: str | None, b: str | None) -> bool:
    """두 풀이가 같은 답인지 — 표기 차이는 흡수하되 값 차이는 절대 흡수하지 않는다."""
    if norm(a) == norm(b):
        return True
    if value_of(a) == value_of(b):
        return True
    # 동치 표기가 하나라도 겹치면 같은 답을 다르게 적은 것이다
    return bool(equiv_set(a) & equiv_set(b))


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
            if not same_answer(aa, ab):
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
