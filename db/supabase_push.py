# -*- coding: utf-8 -*-
"""문제 DB → Supabase 업로드 (멱등 upsert, 변경분만)

체크포인트마다 호출돼 그때까지 판독·채점된 내용을 원격에 올린다. 로컬 PC 가
꺼져도 원격에 남아 있게 하는 것이 목적이라 **재실행이 안전해야** 한다:
같은 행을 다시 올려도 `on_conflict` 로 덮어쓰기만 하고 중복이 생기지 않는다.

  python db/supabase_push.py            변경된 편만 올린다
  python db/supabase_push.py --all      전부 다시 올린다(스키마 바꾼 뒤 등)
  python db/supabase_push.py --dry      올리지 않고 대상만 센다

자격증명(둘 중 아무 데나):
  · 환경변수 SUPABASE_URL / SUPABASE_SERVICE_KEY
  · config.json 의 SUPABASE_URL / SUPABASE_SERVICE_KEY   (gitignore 됨)

⚠️ 테이블은 REST 로 못 만든다. 최초 1회 `db/export/schema.sql` 을 Supabase
   SQL Editor 에 붙여넣어 실행해 둘 것(멱등이라 여러 번 눌러도 안전).
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, sqlite3, sys, io, pathlib, time

BASE = pathlib.Path(__file__).parent
# ⚠️ append 로 붙인다 — insert(0) 이면 db/ 안 모듈이 **표준 라이브러리를
#    가린다**(db/queue.py 가 queue 를 가려 requests 임포트가 죽었다).
sys.path.append(str(BASE))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import scope as _scope                                       # noqa: E402

DB = BASE / "exam_index.db"
STATE = BASE / ".supabase_push.json"
CHUNK = 40                        # 한 요청 행 수. 문항 본문(JSONB)이 커서 크게 잡으면 연결이 끊긴다


def creds() -> tuple[str, str]:
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_ANON_KEY", "")
    cfg = BASE.parent / "config.json"
    if (not url or not key) and cfg.exists():
        try:
            d = json.loads(cfg.read_text(encoding="utf-8"))
            url = url or d.get("SUPABASE_URL", "")
            key = key or d.get("SUPABASE_SERVICE_KEY") or d.get("SUPABASE_ANON_KEY", "")
        except Exception:
            pass
    return url.rstrip("/"), key


def plain_of(q: dict) -> str:
    """검색용 평문 — 수식은 `$...$` 로 남겨 원문 복원이 가능하게."""
    out = []

    def blocks(bs):
        for b in bs or []:
            t, v = (b.get("type") or ""), (b.get("value") or "")
            if t.startswith("equation"):
                out.append(f"${v}$")
            elif t == "figure":
                out.append(f"[그림] {v}")
            elif t == "table":
                rows = b.get("rows") or []
                out.append(" / ".join(" | ".join(str(c) for c in r) for r in rows) or v)
            else:
                out.append(v)

    blocks(q.get("contents"))
    for ch in q.get("choices") or []:
        out.append(f"{ch.get('number', '')}")
        blocks(ch.get("contents"))
    for s in q.get("sub_questions") or []:
        out.append(f"({s.get('number', '')})")
        blocks(s.get("contents"))
    return " ".join(x for x in out if x).strip()


_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def scrub(x):
    """제어문자 제거. ⚠️ Postgres text 는 NUL(\x00)을 거부한다 — 한 글자만
    섞여도 그 배치 전체가 400 으로 튕긴다(실측). 어느 출처든 여기서 막는다."""
    if isinstance(x, str):
        return _CTRL.sub("", x)
    if isinstance(x, list):
        return [scrub(v) for v in x]
    if isinstance(x, dict):
        return {k: scrub(v) for k, v in x.items()}
    return x


def has_figure(q: dict) -> bool:
    return any((b.get("type") == "figure") for b in (q.get("contents") or []))


def post(url: str, key: str, table: str, rows: list[dict], conflict: str,
         depth: int = 0) -> None:
    """upsert 한 묶음. 끊기면 **묶음을 반으로 쪼개** 다시 보낸다.

    문항 본문(JSONB)이 커서 한 요청이 수 MB 가 되면 서버가 응답 없이 연결을
    닫는다(실측). 크기 상한을 고정값으로 정하면 시험지마다 빗나가므로,
    실패했을 때 스스로 줄이게 둔다.
    """
    import requests
    if not rows:
        return
    try:
        r = requests.post(
            f"{url}/rest/v1/{table}",
            params={"on_conflict": conflict},
            headers={"apikey": key, "Authorization": f"Bearer {key}",
                     "Content-Type": "application/json",
                     # merge-duplicates = upsert. 재실행해도 중복이 안 생긴다.
                     "Prefer": "resolution=merge-duplicates,return=minimal"},
            data=json.dumps(scrub(rows), ensure_ascii=False).encode("utf-8"),
            timeout=180)
    except Exception:
        if len(rows) == 1 or depth > 6:
            raise
        mid = len(rows) // 2
        post(url, key, table, rows[:mid], conflict, depth + 1)
        post(url, key, table, rows[mid:], conflict, depth + 1)
        return
    if r.status_code >= 300:
        raise RuntimeError(f"{table} 업로드 실패 {r.status_code}: {r.text[:500]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="변경 여부 무시하고 전부")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    url, key = creds()
    if not a.dry and not (url and key):
        sys.exit("SUPABASE_URL / SUPABASE_SERVICE_KEY 가 없다 — config.json 또는 환경변수에 넣을 것.\n"
                 "  (없이 확인만 하려면 --dry)")

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    # 중복으로 표시된 편은 올리지 않는다 — 원본 쪽이 이미 올라간다
    rows = con.execute(f"""
        SELECT * FROM exams
        WHERE ocr_status='done' AND duplicate_of IS NULL AND {_scope.sql()}
        ORDER BY id""").fetchall()

    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    seen = state.get("exams", {})

    pending_exams, pending_q, skipped = [], [], 0
    for e in rows:
        qs = con.execute("""SELECT number, qtype, ocr_json, answer, solution,
                                   topic, difficulty, answer_source
                            FROM questions WHERE exam_id=? ORDER BY number""",
                         (e["id"],)).fetchall()
        if not qs:
            continue
        # 편 단위 지문 — 문항 내용·정답·해설이 그대로면 다시 올릴 이유가 없다
        sig = hashlib.sha1(
            json.dumps([[q["number"], q["ocr_json"], q["answer"], q["solution"],
                         q["topic"], q["difficulty"], q["answer_source"]] for q in qs],
                       ensure_ascii=False).encode("utf-8")).hexdigest()
        if not a.all and seen.get(str(e["id"])) == sig:
            skipped += 1
            continue

        pending_exams.append({
            "id": e["id"], "level": e["level"], "school": e["school"],
            "grade": e["grade"], "subject": e["subject"], "year": e["year"],
            "semester": e["semester"], "round": e["round"],
            "publisher": e["publisher"], "question_count": len(qs),
            "source_path": e["src_path"],
        })
        for q in qs:
            d = json.loads(q["ocr_json"])
            pending_q.append({
                "exam_id": e["id"], "number": q["number"], "qtype": q["qtype"],
                "score": d.get("score"), "label": d.get("label"),
                "body": d, "plain": plain_of(d),
                "answer": q["answer"], "solution": q["solution"],
                "topic": q["topic"], "difficulty": q["difficulty"],
                "answer_source": q["answer_source"],
                "has_figure": has_figure(d),
            })
        seen[str(e["id"])] = sig
    con.close()

    print(f"범위 {_scope.LABEL} — 대상 {len(rows)}편 중 변경 {len(pending_exams)}편"
          f" / 문항 {len(pending_q):,}  (무변경 건너뜀 {skipped})")
    if a.dry or not pending_exams:
        return

    t0 = time.time()
    for i in range(0, len(pending_exams), CHUNK):
        post(url, key, "exams", pending_exams[i:i + CHUNK], "id")
    for i in range(0, len(pending_q), CHUNK):
        post(url, key, "questions", pending_q[i:i + CHUNK], "exam_id,number")
        print(f"  문항 {min(i + CHUNK, len(pending_q)):,}/{len(pending_q):,}")

    STATE.write_text(json.dumps({"exams": seen}, ensure_ascii=False), encoding="utf-8")
    print(f"업로드 완료 — {len(pending_exams)}편 / {len(pending_q):,}문항  ({time.time()-t0:.0f}초)")


if __name__ == "__main__":
    main()
