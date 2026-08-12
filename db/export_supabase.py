# -*- coding: utf-8 -*-
"""문제 DB → Supabase(Postgres) 업로드용 산출물 생성

  python db/export_supabase.py --out db/export

산출:
  schema.sql   테이블·인덱스·전문검색 DDL (멱등 — 재실행 안전)
  exams.jsonl  시험지 메타
  questions.jsonl  문항(본문 JSONB + 정답·해설·검색용 평문)

업로드는 두 가지 중 편한 쪽:
  · Supabase SQL Editor 에 schema.sql 붙여넣기 → 대시보드에서 JSONL 임포트
  · psql: \\copy 로 jsonl 을 임시테이블에 넣고 jsonb 파싱해 삽입
"""
from __future__ import annotations
import argparse, json, re, sqlite3, sys, io, pathlib

BASE = pathlib.Path(__file__).parent
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
DB = BASE / "exam_index.db"

SCHEMA = """
-- 문제 DB (시험지·문항). 재실행 안전.
create table if not exists exams (
  id            integer primary key,
  level         text,           -- 중 / 고
  school        text not null,
  grade         smallint,
  subject       text,
  year          smallint,
  semester      smallint,
  round         text,           -- 중간 / 기말
  publisher     text,
  question_count smallint,
  source_path   text,
  created_at    timestamptz default now()
);

create table if not exists questions (
  id            bigserial primary key,
  exam_id       integer not null references exams(id) on delete cascade,
  number        smallint not null,
  qtype         text,           -- 객관식 / 단답형 / 서술형
  score         real,
  label         text,           -- [서술형 1] 등
  body          jsonb not null, -- contents/choices/sub_questions 원본
  plain         text,           -- 검색용 평문(수식은 $...$)
  answer        text,
  solution      text,
  topic         text,
  difficulty    text,
  has_figure    boolean default false,
  unique (exam_id, number)
);

create index if not exists ix_exams_meta
  on exams (year, level, grade, semester, round, subject);
create index if not exists ix_exams_school on exams (school);
create index if not exists ix_q_exam on questions (exam_id);
create index if not exists ix_q_type on questions (qtype);
create index if not exists ix_q_topic on questions (topic);

-- 발문 전문검색 (한국어는 simple 로도 부분일치 검색 가능)
create index if not exists ix_q_plain_fts
  on questions using gin (to_tsvector('simple', coalesce(plain, '')));

-- 참고: 수식 포함 유사문항 탐색은 plain 의 trigram 이 유용하다
create extension if not exists pg_trgm;
create index if not exists ix_q_plain_trgm
  on questions using gin (plain gin_trgm_ops);
"""


def plain_of(q: dict) -> str:
    out = []
    for b in q.get("contents") or []:
        t, v = b.get("type"), b.get("value") or ""
        out.append(f"${v}$" if (t or "").startswith("equation")
                   else (f"[그림] {v}" if t == "figure" else v))
    for ch in q.get("choices") or []:
        vals = " ".join(
            (f"${b['value']}$" if (b.get('type') or '').startswith('equation')
             else (b.get('value') or ''))
            for b in ch.get("contents") or [])
        out.append(f"({ch.get('number')}) {vals}")
    for s in q.get("sub_questions") or []:
        vals = " ".join((b.get("value") or "") for b in s.get("contents") or [])
        out.append(f"({s.get('number')}) {vals}")
    return re.sub(r"\s{2,}", " ", " ".join(out)).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="db/export")
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    (out / "schema.sql").write_text(SCHEMA.lstrip(), encoding="utf-8")

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    # 문항이 실제로 적재된 시험지만 내보낸다
    exams = con.execute("""
      SELECT e.* FROM exams e
      WHERE EXISTS (SELECT 1 FROM questions q WHERE q.exam_id=e.id)
      ORDER BY e.id""").fetchall()

    with (out / "exams.jsonl").open("w", encoding="utf-8") as f:
        for e in exams:
            f.write(json.dumps({
                "id": e["id"], "level": e["level"], "school": e["school"],
                "grade": e["grade"], "subject": e["subject"], "year": e["year"],
                "semester": e["semester"], "round": e["round"],
                "publisher": e["publisher"], "question_count": e["question_count"],
                "source_path": e["src_path"],
            }, ensure_ascii=False) + "\n")

    n_q = n_fig = 0
    with (out / "questions.jsonl").open("w", encoding="utf-8") as f:
        for r in con.execute("""SELECT * FROM questions ORDER BY exam_id, number"""):
            q = json.loads(r["ocr_json"])
            blocks = (q.get("contents") or [])
            has_fig = any(b.get("type") == "figure" for b in blocks)
            n_fig += has_fig
            f.write(json.dumps({
                "exam_id": r["exam_id"], "number": r["number"],
                "qtype": r["qtype"], "score": q.get("score"),
                "label": q.get("label"),
                "body": {"contents": q.get("contents") or [],
                         "choices": q.get("choices") or [],
                         "sub_questions": q.get("sub_questions") or []},
                "plain": plain_of(q),
                "answer": r["answer"], "solution": r["solution"],
                "topic": r["topic"], "difficulty": r["difficulty"],
                "has_figure": has_fig,
            }, ensure_ascii=False) + "\n")
            n_q += 1
    con.close()

    print(f"시험지 {len(exams):,}편 / 문항 {n_q:,}개 (그림 포함 {n_fig:,})")
    for p in ("schema.sql", "exams.jsonl", "questions.jsonl"):
        sz = (out / p).stat().st_size
        print(f"  {p:<18} {sz/1024:,.0f} KB")
    print(f"\n출력: {out.resolve()}")


if __name__ == "__main__":
    main()
