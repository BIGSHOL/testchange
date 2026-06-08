# 위험토큰 감사(②) — OCR 출력 JSON 을 스캔해 '사람이 다시 봐야 할' 토큰을 표시.
#
# 골든·API 불필요(stdlib only). 단일 OCR 출력만으로 작동 → 키 없이 지금 바로 쓸 수 있다.
#
# 사용법:
#   python scripts/ocr_eval/audit_ocr.py tests/golden_ocr            # 디렉터리 전체
#   python scripts/ocr_eval/audit_ocr.py .testkit/ocr_eval/<stem>/<sig>   # eval 캐시
#   python scripts/ocr_eval/audit_ocr.py some_crop.json --severity low   # low 까지
#   python scripts/ocr_eval/audit_ocr.py tests/golden_ocr --json     # 기계가독 출력
#
# 입력 JSON 은 둘 다 받는다:
#   - 골든 레코드  {..., "golden": {"header", "questions": [...]}}
#   - bare OCR 출력 {"header", "questions": [...]}  (eval 캐시 p{i}_c{ci}.json)
#
# 출력은 severity 별 그룹(기본 medium↑ — 수학 시험지 노이즈 억제). low 는 --severity low 일 때만.
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.ocr_eval.risk_tokens import audit_blocks

_SEV_ORDER = ["high", "medium", "low"]


def _extract_questions(doc) -> list[dict]:
    """골든 레코드(doc['golden'])든 bare OCR 출력(doc)이든 questions 리스트로 정규화."""
    if not isinstance(doc, dict):
        return []
    if isinstance(doc.get("golden"), dict):
        doc = doc["golden"]
    qs = doc.get("questions")
    return [q for q in qs if isinstance(q, dict)] if isinstance(qs, list) else []


def _iter_json_files(target: Path):
    if target.is_dir():
        yield from sorted(target.glob("*.json"))
    elif target.is_file():
        yield target


def audit_path(target: Path, min_severity: str) -> list[dict]:
    """대상 경로(파일/디렉터리)의 모든 JSON 을 감사 → 플래그 리스트(sample 정보 포함)."""
    all_flags: list[dict] = []
    for fp in _iter_json_files(target):
        # metadata.json·scores.jsonl 등 비-OCR 산출물은 건너뛴다.
        if fp.name in ("metadata.json",) or fp.suffix != ".json":
            continue
        try:
            doc = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        questions = _extract_questions(doc)
        if not questions:
            continue
        sample = (doc.get("sample_id") if isinstance(doc, dict) else None) or fp.stem
        for flag in audit_blocks(questions, min_severity):
            flag = dict(flag, sample=sample)
            all_flags.append(flag)
    return all_flags


def _print_report(flags: list[dict]) -> None:
    if not flags:
        print("위험토큰 없음(현 severity 기준).")
        return
    by_sev: dict[str, list[dict]] = {s: [] for s in _SEV_ORDER}
    for f in flags:
        by_sev.setdefault(f.get("severity", "low"), []).append(f)
    total = len(flags)
    print(f"위험토큰 {total}건 ── severity 순\n")
    for sev in _SEV_ORDER:
        group = by_sev.get(sev) or []
        if not group:
            continue
        print(f"[{sev.upper()}] {len(group)}건")
        for f in group:
            q = f.get("q_number")
            qs = f"#{q}" if q is not None else "#?"
            reason = f"  ({f['reason']})" if f.get("reason") else ""
            print(f"  {f['sample']} {qs} {f['category']:<20} "
                  f"{f['block_type']:<14} ⟨{f['token']}⟩{reason}")
        print()
    # 카테고리 요약(군집 한눈에).
    cats: dict[str, int] = {}
    for f in flags:
        cats[f["category"]] = cats.get(f["category"], 0) + 1
    print("── 카테고리 요약 ──")
    for cat, n in sorted(cats.items(), key=lambda kv: -kv[1]):
        print(f"  {cat:<22} {n}")


def main(argv):
    positional = [a for a in argv if not a.startswith("--")]
    if not positional:
        raise SystemExit(
            "사용법: python scripts/ocr_eval/audit_ocr.py <파일|디렉터리> "
            "[--severity high|medium|low] [--json]")
    target = Path(positional[0])
    if not target.exists():
        raise SystemExit(f"경로 없음: {target}")

    min_severity = "medium"
    for a in argv:
        if a.startswith("--severity="):
            min_severity = a.split("=", 1)[1].strip()
    if "--severity" in argv:  # 공백 구분형 지원
        i = argv.index("--severity")
        if i + 1 < len(argv):
            min_severity = argv[i + 1]
    if min_severity not in _SEV_ORDER:
        raise SystemExit(f"--severity 는 high|medium|low 중 하나여야 합니다: {min_severity}")

    flags = audit_path(target, min_severity)
    if "--json" in argv:
        print(json.dumps(flags, ensure_ascii=False, indent=2))
    else:
        _print_report(flags)


if __name__ == "__main__":
    main(sys.argv[1:])
