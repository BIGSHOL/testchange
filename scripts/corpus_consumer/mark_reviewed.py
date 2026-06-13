# 격리 worktree 에서 corpus 핸드오프를 reviewed 로 마킹 (auto 모드 헬퍼).
# status=reviewed + review 블록 주입, 나머지 meta 보존. 멱등(이미 reviewed 면 skip).
# 사용법: python mark_reviewed.py "<corpus 폴더>" "<review note>"
import sys, json
from pathlib import Path

folder, note = sys.argv[1], sys.argv[2]
mj = Path(folder) / "meta.json"
d = json.loads(mj.read_text(encoding="utf-8"))
if str(d.get("status", "")).startswith("reviewed"):
    print("already reviewed:", folder); sys.exit(0)
was = d.get("status")
rest = {k: v for k, v in d.items() if k != "status"}
out = {
    "status": "reviewed",
    "review": {
        "reviewed_date": "2026-06-13",
        "reviewed_by": "렌더/검수 소비자 세션 (claude-opus-4-8[1m], 격리 worktree render-review)",
        "content_defects": 0, "A_type": 0, "B_type": 0,
        "note": note,
    },
    "status_was": was,
    **rest,
}
mj.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print("marked reviewed:", folder)
