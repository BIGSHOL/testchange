# 보강 프롬프트 반자동 제작(④) — 골든↔후보 실패를 채굴·군집해 **보강 리포트** 생성.
#
# 이 루틴은 **결정적 실패 리포트 + 규칙기반 스켈레톤만** 만든다(API 0원). LLM 초안은 별도 호출
# 대신 **Claude Code 세션의 사람-옆-에이전트가** 이 리포트를 읽고 보강 블록을 정련한다. 그리고
# **사람 승인 후에만** core/ocr_reinforcement.md 에 반영한다(이 스크립트는 절대 자동반영 안 함).
#
# 사용법:
#   python scripts/ocr_eval/suggest_reinforcement.py "<PDF stem>"          # 최근 sig 후보
#   python scripts/ocr_eval/suggest_reinforcement.py "<PDF stem>" --sig=<sig>
#
# 후보(candidate) = .testkit/ocr_eval/<stem>/<sig>/p{i}_c{ci}.json (실모델 OCR 출력).
# 키 만료/캐시 없음이면: 후보 부재를 명확히 안내하고 스켈레톤만 낸다(메커니즘은 단위테스트가 담보).
#
# 산출물: .testkit/ocr_eval/suggestions/<sig>_<stamp>.md  (제안만 — 파일 미반영)
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.ocr_eval.failures import cluster_by_category, diff_crop

_TESTKIT = REPO / ".testkit"
EVAL_ROOT = _TESTKIT / "ocr_eval"
GOLDEN_DIR = REPO / "tests" / "golden_ocr"
SUGGEST_DIR = EVAL_ROOT / "suggestions"

# 카테고리별 규칙기반 보강 스켈레톤(Claude Code 가 실패 예시를 보고 정련할 출발점).
_SKELETON: dict[str, str] = {
    "HOL_JJAK": "- '홀수'/'짝수' 는 한 글자로 정답이 뒤집힌다. 인쇄된 글자를 그대로 옮기고, "
                "추론으로 바꾸지 말 것. 애매하면 본문 그대로.",
    "DECIMAL": "- 소수는 자릿수를 **있는 그대로** 옮긴다(172.44 를 172.4 로 줄이거나 늘리지 "
               "말 것). 표/확률값의 끝자리 0 도 보존.",
    "CONFIDENCE_INTERVAL": "- 신뢰구간·신뢰도·오차범위(±) 표기는 숫자·부등호·괄호를 통째로 "
                           "정확히. 구간 양 끝값을 바꾸거나 합치지 말 것.",
    "INEQUALITY": "- 부등호 방향(<, >, ≤, ≥)을 절대 뒤집지 말 것. 인쇄 기호 그대로.",
    "EXPONENT": "- 지수(위첨자)의 숫자를 그대로(2^{48} 을 2^{6} 으로 줄이지 말 것). 중첩 "
                "위첨자 괄호 보존.",
    "TABLE_COUNT": "- 표(확률분포표·정규분포표)를 요약·누락하지 말고 모든 행·열 셀을 옮긴다.",
    "FIGURE_COUNT": "- 그림 블록의 존재/개수를 임의로 바꾸지 말 것.",
    "CHOICE_COUNT": "- 선택지 ①~⑤ 개수를 빠뜨리거나 더하지 말 것.",
    "NUMBER": "- 숫자의 자릿수·값을 그대로 옮긴다.",
}


def _load_golden_for_stem(stem: str) -> list[dict]:
    """골든 디렉터리에서 해당 PDF stem 의 레코드만(stdlib·json — score_ocr 로더의 안전 복제)."""
    out = []
    for fp in sorted(GOLDEN_DIR.glob("*.json")):
        try:
            rec = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if rec.get("source", {}).get("pdf_stem") == stem:
            out.append(rec)
    return out


def _resolve_sig_dir(stem: str, sig: str | None) -> Path | None:
    stem_dir = EVAL_ROOT / stem
    if not stem_dir.exists():
        return None
    if sig:
        d = stem_dir / sig
        return d if d.exists() else None
    sig_dirs = sorted([d for d in stem_dir.iterdir() if d.is_dir()],
                      key=lambda d: d.stat().st_mtime, reverse=True)
    return sig_dirs[0] if sig_dirs else None


def _candidate(eval_dir: Path | None, i, ci):
    if eval_dir is None:
        return None
    fp = eval_dir / f"p{i}_c{ci}.json"
    if fp.exists():
        try:
            return json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _mine(stem: str, sig: str | None):
    """골든 + (가능하면) 후보 캐시로 실패 채굴 → (mismatches, n_pairs, eval_dir)."""
    goldens = _load_golden_for_stem(stem)
    if not goldens:
        raise SystemExit(
            f"'{stem}' 골든이 tests/golden_ocr 에 없습니다 — golden_record.py 로 먼저 시딩하세요.")
    eval_dir = _resolve_sig_dir(stem, sig)
    mismatches = []
    n_pairs = 0
    for rec in goldens:
        src = rec.get("source", {})
        cand = _candidate(eval_dir, src.get("i"), src.get("ci"))
        if cand is None:
            continue
        n_pairs += 1
        mismatches.extend(
            diff_crop(cand, rec.get("golden", {}), rec.get("sample_id", "")))
    return mismatches, n_pairs, eval_dir, len(goldens)


def _render_report(stem, sig, eval_dir, n_golden, n_pairs, clusters) -> str:
    stamp = datetime.now(timezone.utc).isoformat()
    lines = [
        f"# OCR 보강 제안 — {stem}",
        "",
        f"- 생성: {stamp}",
        f"- 골든 샘플: {n_golden} / 후보 매칭: {n_pairs}",
        f"- eval 후보 sig: {eval_dir.name if eval_dir else '(없음)'}",
        "",
        "> ⚠️ 이 파일은 **제안**이다. core/ocr_reinforcement.md 에 자동 반영하지 않는다.",
        "> Claude Code 세션의 에이전트가 아래 실패를 읽고 보강 블록을 정련한 뒤, **사람 승인** "
        "후에만 core/ocr_reinforcement.md 에 추가한다. 추가 후 prompt_signature 가 바뀌고 "
        "score_ocr --baseline --candidate 로 개선·무회귀를 확인한다(B 단계).",
        "",
    ]

    if n_pairs == 0:
        lines += [
            "## ⚠️ 후보(candidate) 없음 — 실측 채굴 불가",
            "",
            "eval 캐시(.testkit/ocr_eval/<stem>/<sig>/p{i}_c{ci}.json)에 실모델 OCR 후보가 "
            "없어 골든↔후보 실패를 채굴하지 못했다. 둘 중 하나로 후보를 만든 뒤 다시 실행:",
            "",
            "1. (API 키 필요) `python scripts/crop_dump.py <PDF>` → "
            "`python scripts/ocr_eval/score_ocr.py <PDF> --reocr`",
            "2. 메커니즘 검증만 원하면 `python tests/test_ocr_failures.py` (합성쌍, 키 0).",
            "",
            "아래는 **일반 규칙기반 스켈레톤**(실패 예시 없이도 항상 유효한 보강 출발점)이다.",
            "",
            "## 보강 스켈레톤(규칙기반)",
            "",
        ]
        for cat, skel in _SKELETON.items():
            lines.append(f"### {cat}")
            lines.append(skel)
            lines.append("")
        lines += _claude_section()
        return "\n".join(lines)

    # 실측 채굴 있음.
    lines.append(f"## 채굴된 실패 {sum(len(v) for v in clusters.values())}건 — 카테고리별\n")
    for cat, items in sorted(clusters.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"### {cat} ({len(items)}건)")
        # 대표 예시 최대 8개.
        for m in items[:8]:
            lines.append(
                f"- [{m.sample_id}] {m.kind}: 골든 ⟨{m.golden}⟩ ↔ 후보 ⟨{m.candidate}⟩")
        if len(items) > 8:
            lines.append(f"- … 외 {len(items) - 8}건")
        skel = _SKELETON.get(cat)
        if skel:
            lines.append("")
            lines.append("**보강 스켈레톤:**")
            lines.append(skel)
        lines.append("")
    lines += _claude_section()
    return "\n".join(lines)


def _claude_section() -> list[str]:
    return [
        "## Claude Code 정련 자리",
        "",
        "위 실패/스켈레톤을 **일반 규칙**으로 군집해(인스턴스별 암기 금지) 아래 형식의 보강 "
        "블록을 작성한다. 분량 상한을 지키고, 골든이 막는 회귀를 뚫지 말 것.",
        "",
        "```",
        "## (카테고리) 보강 — YYYY-MM-DD",
        "- <원본 그대로 옮겨라류 일반 규칙 1>",
        "- <일반 규칙 2>",
        "```",
        "",
        "## 적용 절차(사람 승인 후)",
        "1. 위 블록을 `core/ocr_reinforcement.md` 에 추가(base 프롬프트는 불변).",
        "2. `python -c \"from scripts.ocr_eval.prompt_version import prompt_signature; "
        "print(prompt_signature())\"` 로 sig 변경 확인(B 단계 연결 후).",
        "3. `score_ocr --reocr` 로 새 후보 생성 → `score_ocr --baseline=<old> "
        "--candidate=<new>` 로 개선·무회귀(문항별 회귀목록) 확인 후 채택/되돌림.",
    ]


def main(argv):
    positional = [a for a in argv if not a.startswith("--")]
    if not positional:
        raise SystemExit(
            "사용법: python scripts/ocr_eval/suggest_reinforcement.py <PDF stem> [--sig=<sig>]")
    stem = positional[0]
    sig = None
    for a in argv:
        if a.startswith("--sig="):
            sig = a.split("=", 1)[1].strip()

    mismatches, n_pairs, eval_dir, n_golden = _mine(stem, sig)
    clusters = cluster_by_category(mismatches)

    SUGGEST_DIR.mkdir(parents=True, exist_ok=True)
    sig_label = (eval_dir.name if eval_dir else "nosig")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_fp = SUGGEST_DIR / f"{sig_label}_{stamp}.md"
    out_fp.write_text(
        _render_report(stem, sig, eval_dir, n_golden, n_pairs, clusters),
        encoding="utf-8")

    print(f"골든={n_golden} 후보매칭={n_pairs} 실패채굴={len(mismatches)}")
    if n_pairs == 0:
        print("⚠️ 후보 없음 — 스켈레톤만 생성(실측 채굴은 키 필요 또는 단위테스트로 검증).")
    print(f"wrote: {out_fp}")


if __name__ == "__main__":
    main(sys.argv[1:])
