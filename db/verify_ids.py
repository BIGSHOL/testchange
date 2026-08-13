# -*- coding: utf-8 -*-
"""인덱스 재구축 후 exam id 안정성 대조 — 판독 결과가 엉뚱한 시험지에 붙는 것 차단

`build_index.py` 는 DB 를 지우고 다시 만들며 id 를 **정렬 순서대로** 부여한다.
그래서 N: 파일이 늘거나 줄면 id 가 통째로 밀리고, 이미 판독한
`db/ocr_pilot/<id>.json` 이 다른 시험지에 매달린다(조용히 오염된다).

이 스크립트는 판독 JSON 이 스스로 들고 있는 메타(`meta` 또는 `header.title`)를
재구축된 DB 행과 대조한다. **재구축 직후 항상 돌릴 것.**

  python db/verify_ids.py            대조 결과 요약
  python db/verify_ids.py --remap    어긋난 건의 올바른 id 후보까지 제시(변경 없음)
"""
from __future__ import annotations
import argparse, json, re, sqlite3, sys, io, pathlib

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = pathlib.Path(__file__).parent
DB = BASE / "exam_index.db"
SRC = BASE / "ocr_pilot"
EXTRACTED = BASE / "extracted"
MANIFEST = BASE / "solve" / "manifest.json"

# `[강동고][1][공수2][25-2-중간]` (manifest tag) / `_강동고__1__공수2__25-2-중간대비_` (원본 파일명)
_TERM = re.compile(r"(\d{2})-([12])-(중간|기말)")
# "중간고사"·"기말고사" 가 학교명(…고)으로 잡히면 멀쩡한 편이 불일치로 뜬다
_SCHOOL = re.compile(r"(?!중간|기말|모의)([가-힣]{2,10}(?:여고|여중|고|중))(?!사)")


def _from_tokens(toks: list[str]) -> dict:
    """[학교][학년][과목][YY-학기-회차] 토큰 → 메타. manifest·원본 파일명 공용."""
    out: dict = {}
    for t in toks:
        t = t.strip()
        if not t:
            continue
        if (m := _TERM.search(t)):
            out.update(year=2000 + int(m.group(1)), semester=int(m.group(2)), round=m.group(3))
        elif re.fullmatch(r"[1-3]", t):
            out.setdefault("grade", int(t))
        elif _SCHOOL.fullmatch(t):
            out.setdefault("school", t)
    return out


def _manifest_tags() -> dict[int, dict]:
    if not MANIFEST.exists():
        return {}
    out = {}
    for it in json.loads(MANIFEST.read_text(encoding="utf-8")):
        out[int(it["id"])] = _from_tokens(re.findall(r"\[([^\[\]]*)\]", it.get("tag") or ""))
    return out


def json_meta(d: dict, eid: int | None = None, tags: dict | None = None) -> dict:
    """학교·학년·연도·학기·회차를 뽑는다.

    근거 우선순위: ① 판독 JSON 의 meta ② 정답 추출본의 원본 파일명(`source`)
    ③ solve manifest 태그 ④ 제목. 뒤로 갈수록 약해서, 앞선 근거를 덮지 않는다.
    """
    m = d.get("meta") or {}
    out = {k: m.get(k) for k in ("school", "grade", "subject", "year", "semester", "round")}
    if out.get("school") and out.get("year"):
        return out

    def fill(src: dict):
        for k, v in src.items():
            if v and not out.get(k):
                out[k] = v

    if eid is not None:
        f = EXTRACTED / f"{eid}.json"
        if f.exists():
            src = (json.loads(f.read_text(encoding="utf-8")).get("source") or "")
            fill(_from_tokens(re.split(r"[_\[\]]+", pathlib.Path(src).stem)))
        fill((tags or {}).get(eid, {}))

    t = (d.get("header") or {}).get("title") or ""
    if (mm := _SCHOOL.search(t)):
        fill({"school": mm.group(1)})
    if (mm := re.search(r"([1-3])\s*학년(?!도)", t)):
        fill({"grade": int(mm.group(1))})
    if (mm := re.search(r"(20\d{2})\s*(?:학년도|년)", t)):
        fill({"year": int(mm.group(1))})
    if (mm := re.search(r"([12])\s*학기", t)):
        fill({"semester": int(mm.group(1))})
    if (mm := re.search(r"(중간|기말)", t)):
        fill({"round": mm.group(1)})
    return out


def row_of(con, eid: int):
    return con.execute("""SELECT school,grade,subject,year,semester,round
                          FROM exams WHERE id=?""", (eid,)).fetchone()


def norm_school(s: str | None) -> str:
    """학교명 표기 흡수 — 시험지 인쇄는 정식명, 파일명은 축약이라 그냥 비교하면 다 어긋난다.

    `사직여자고등학교` ≡ `사직여고`, `매천고등학교` ≡ `매천고`.
    """
    s = re.sub(r"\s+", "", s or "")
    s = re.sub(r"등학교$", "", s)            # 고등학교→고, 중등학교→중
    s = s.replace("학교", "")
    s = s.replace("여자고", "여고").replace("여자중", "여중")
    return s


def agree(meta: dict, row) -> tuple[bool, str]:
    """비교는 **JSON 이 실제로 아는 항목만**. 제목에서 못 뽑은 값은 판정 근거가 아니다."""
    if row is None:
        return False, "DB 에 해당 id 없음"
    school, grade, subject, year, semester, rnd = row
    bad = []
    if meta.get("school") and norm_school(meta["school"]) != norm_school(school):
        bad.append(f"학교 {meta['school']}≠{school}")
    if meta.get("grade") and row[1] and int(meta["grade"]) != int(grade):
        bad.append(f"학년 {meta['grade']}≠{grade}")
    if meta.get("year") and year and int(meta["year"]) != int(year):
        bad.append(f"연도 {meta['year']}≠{year}")
    if meta.get("semester") and semester and int(meta["semester"]) != int(semester):
        bad.append(f"학기 {meta['semester']}≠{semester}")
    if meta.get("round") and rnd and meta["round"] != rnd:
        bad.append(f"회차 {meta['round']}≠{rnd}")
    if not any(meta.get(k) for k in ("school", "year")):
        return False, "판정 근거 없음(메타·제목 모두 빈약) — 수동 확인"
    return (not bad), ", ".join(bad)


def candidates(con, meta: dict):
    where, args = [], []
    for col, key in (("school", "school"), ("grade", "grade"), ("year", "year"),
                     ("semester", "semester"), ("round", "round")):
        if meta.get(key):
            where.append(f"{col}=?"); args.append(meta[key])
    if not where:
        return []
    return con.execute(f"SELECT id,school,grade,subject,year,semester,round "
                       f"FROM exams WHERE {' AND '.join(where)}", args).fetchall()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--remap", action="store_true")
    a = ap.parse_args()
    if not DB.exists():
        sys.exit(f"DB 없음: {DB}  — 먼저 scan_inventory.py → build_index.py")

    con = sqlite3.connect(DB)
    tags = _manifest_tags()
    files = sorted((p for p in SRC.glob("*.json") if not p.name.endswith(".answers.json")),
                   key=lambda p: int(p.stem))
    ok, shifted, mislabeled, weak = 0, [], [], 0
    for p in files:
        d = json.loads(p.read_text(encoding="utf-8"))
        meta = json_meta(d, int(p.stem), tags)
        good, why = agree(meta, row_of(con, int(p.stem)))
        if good:
            ok += 1
        elif "판정 근거 없음" in why:
            weak += 1
            print(f"  ?    {p.stem}  {why}")
        # ⚠️ 학교가 어긋나야 id 밀림이다. 학교는 맞는데 학년·학기만 다르면
        #    **파일명(카탈로그) 오라벨**이지 매핑 사고가 아니다 — 이 둘을 뭉뚱그리면
        #    멀쩡한 파이프라인을 멈춰 세운다(실제로 4건에 오진했다).
        elif "학교 " in why or "DB 에 해당 id 없음" in why:
            shifted.append((p.stem, meta, why))
            print(f"  X    {p.stem}  {why}")
        else:
            mislabeled.append((p.stem, meta, why))
            print(f"  !    {p.stem}  {why}   (인쇄 기준 — 파일명 라벨 오류로 보임)")

    print(f"\n대조 {len(files)}편 — 일치 {ok}, id 밀림 {len(shifted)},"
          f" 라벨 불일치 {len(mislabeled)}, 판정불가 {weak}")
    if (shifted or mislabeled) and a.remap:
        print("\n--- 올바른 id 후보 (변경하지 않음) ---")
        for eid, meta, _ in shifted + mislabeled:
            for c in candidates(con, meta) or [("(후보 없음)",)]:
                print(f"  {eid} → {c}")
    if mislabeled:
        print("\n· 라벨 불일치 = 판독물은 제 자리에 있고 **카탈로그 메타가 틀린** 것이다."
              " 시험지에 인쇄된 값이 근거이므로 exams 행을 고치면 된다(판독 재실행 불필요).")
    if shifted:
        print("\n⚠️ id 가 밀렸다. 판독 JSON 을 이 인덱스로 그냥 쓰면 안 된다 —"
              " 스캔 범위를 원래대로 맞추거나(권장) 후보를 보고 파일명을 옮길 것.")
        sys.exit(1)
    con.close()


if __name__ == "__main__":
    main()
