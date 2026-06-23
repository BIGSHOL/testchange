# corpus 핸드오프를 reviewed 로 마킹 (단일 master, auto 모드 헬퍼).
# status=reviewed + review 블록 주입, 나머지 meta 보존. 멱등(이미 reviewed 면 skip).
# 사용법: python mark_reviewed.py "<corpus 폴더>" "<review note>" [B_type수]
import sys, json, datetime
from pathlib import Path

folder, note = sys.argv[1], sys.argv[2]
b_type = int(sys.argv[3]) if len(sys.argv) > 3 else 0  # 검수서 발견·수정한 코드결함 수
mj = Path(folder) / "meta.json"
d = json.loads(mj.read_text(encoding="utf-8"))
if str(d.get("status", "")).startswith("reviewed"):
    print("already reviewed:", folder); sys.exit(0)
was = d.get("status")
rest = {k: v for k, v in d.items() if k != "status"}
out = {
    "status": "reviewed",
    "review": {
        "reviewed_date": datetime.date.today().isoformat(),
        "reviewed_by": "비전 1:1 검수 소비자 세션 (claude-opus-4-8, 단일 master)",
        "content_defects": 0, "A_type": 0, "B_type": b_type,
        "note": note,
    },
    "status_was": was,
    **rest,
}
mj.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print("marked reviewed:", folder)
