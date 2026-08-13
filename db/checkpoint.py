# -*- coding: utf-8 -*-
"""문항 1,000개마다 커밋·푸시 체크포인트

작업 중 PC 가 꺼진 사례가 있어, 판독 결과를 원격에 주기적으로 남긴다.
**db/ 만 커밋**한다 — 이 저장소는 여러 세션이 동시에 쓰므로 `git add -A` 로
남의 미커밋 작업을 삼키면 안 된다(CLAUDE.md 규약).

  python db/checkpoint.py           1000 경계를 넘었으면 커밋(+푸시)
  python db/checkpoint.py --force   경계와 무관하게 지금 커밋
  python db/checkpoint.py --no-push 커밋만
"""
from __future__ import annotations
import argparse, json, sqlite3, subprocess, sys, io, pathlib, datetime

BASE = pathlib.Path(__file__).parent
ROOT = BASE.parent
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
DB = BASE / "exam_index.db"
STATE = BASE / ".checkpoint.json"
STEP = 1000
REMOTE = "testchange"


def sh(*args: str, check: bool = True) -> str:
    r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(args)}\n{r.stdout}\n{r.stderr}")
    return (r.stdout or "").strip()


def stats() -> dict:
    con = sqlite3.connect(DB)
    q = con.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    e = con.execute("SELECT COUNT(*) FROM exams WHERE ocr_status='done'").fetchone()[0]
    a = con.execute("""SELECT COUNT(*) FROM questions
                       WHERE answer IS NOT NULL AND answer<>''""").fetchone()[0]
    con.close()
    return {"questions": q, "exams": e, "answers": a}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument("--no-upload", action="store_true",
                    help="Supabase 업로드 생략(커밋·푸시만)")
    a = ap.parse_args()

    s = stats()
    last = 0
    if STATE.exists():
        last = json.loads(STATE.read_text(encoding="utf-8")).get("questions", 0)

    crossed = (s["questions"] // STEP) > (last // STEP)
    print(f"문항 {s['questions']:,} (직전 체크포인트 {last:,})  "
          f"시험지 {s['exams']:,}  정답 {s['answers']:,}")
    if not crossed and not a.force:
        nxt = ((s["questions"] // STEP) + 1) * STEP
        print(f"  다음 체크포인트까지 {nxt - s['questions']:,}문항 — 커밋 안 함")
        return

    # db/ 만 — 다른 세션의 미커밋 변경을 건드리지 않는다
    sh("git", "add", "db/")
    if not sh("git", "diff", "--cached", "--name-only"):
        print("  변경 없음 — 커밋 생략")
        return

    n_files = len(sh("git", "diff", "--cached", "--name-only").splitlines())
    today = datetime.date.today().isoformat()
    msg = (f"data(db): 문제 DB 체크포인트 — {s['exams']:,}편 {s['questions']:,}문항 "
           f"(정답 {s['answers']:,}, {s['answers']/max(1,s['questions'])*100:.1f}%)\n\n"
           f"판독 결과 JSON {n_files}개 갱신. {today}.\n"
           f"pages/·*.db·export/ 는 재생성 가능해 제외(gitignore).")
    sh("git", "commit", "-q", "-m", msg)
    print(f"  커밋: {sh('git', 'log', '--oneline', '-1')}")

    if not a.no_push:
        try:
            sh("git", "push", REMOTE, "HEAD:master")
            print(f"  푸시 완료 → {REMOTE}")
        except Exception as ex:
            print(f"  ⚠️ 푸시 실패(커밋은 남음): {str(ex)[:200]}")

    # Supabase 업로드도 체크포인트에 묶는다(사용자 지시 2026-08-13).
    # ⚠️ 실패해도 커밋·푸시는 이미 끝났으므로 **중단하지 않는다** — 자격증명이
    #    없는 PC 에서도 판독은 계속 굴러야 한다. 업로더는 멱등이라 다음 번에
    #    밀린 분까지 함께 올라간다.
    if not a.no_upload:
        try:
            print(sh(sys.executable, str(BASE / "supabase_push.py")))
        except Exception as ex:
            print(f"  ⚠️ Supabase 업로드 건너뜀: {str(ex).splitlines()[-1][:160]}")

    STATE.write_text(json.dumps({**s, "at": today}, ensure_ascii=False),
                     encoding="utf-8")


if __name__ == "__main__":
    main()
