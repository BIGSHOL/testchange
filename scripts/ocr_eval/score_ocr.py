# 채점 러너 — 골든셋 vs 현재 프롬프트 후보 OCR 채점(프롬프트 A/B·회귀 측정).
#
# 사용법:
#   python scripts/ocr_eval/score_ocr.py <PDF>            # eval 캐시 있으면 API 0원
#   python scripts/ocr_eval/score_ocr.py <PDF> --reocr    # 현 프롬프트로 후보 재생성(과금)
#   python scripts/ocr_eval/score_ocr.py <PDF> --reocr=12,18   # 해당 문항만 재OCR
#   python scripts/ocr_eval/score_ocr.py <PDF> --baseline=<sig> --candidate=<sig>  # A/B
#
# 후보(candidate) = recognize_crop 의 **raw 출력**(resolve_figs 미적용 — figure 채점 위해).
# prompt_signature 별 디렉터리에 캐시하므로, 한 번 OCR 한 프롬프트는 이후 채점이 0원.
#
# eval 캐시 구조: .testkit/ocr_eval/<stem>/<sig>/{metadata.json, p{i}_c{ci}.json, scores.jsonl, summary.csv}
import csv
import json
import os
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.ocr_eval.metrics import aggregate, score_crop
from scripts.ocr_eval.prompt_version import metadata as prompt_metadata, prompt_signature

_TESTKIT_DIR = REPO / ".testkit"
OCR_CACHE_ROOT = os.environ.get("TESTKIT_CACHE", str(_TESTKIT_DIR / "ocr_cache"))
EVAL_ROOT = str(_TESTKIT_DIR / "ocr_eval")
GOLDEN_DIR = REPO / "tests" / "golden_ocr"


def _load_golden_for_stem(stem: str) -> list[dict]:
    out = []
    for fp in sorted(GOLDEN_DIR.glob("*.json")):
        try:
            rec = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if rec.get("source", {}).get("pdf_stem") == stem:
            out.append(rec)
    return out


def _candidate_from_cache(eval_dir: Path, i, ci):
    fp = eval_dir / f"p{i}_c{ci}.json"
    if fp.exists():
        try:
            return json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _reocr(stem: str, i, ci, eval_dir: Path):
    """크롭 PNG 를 recognize_crop 으로 OCR 해 raw 출력을 eval 캐시에 저장 후 반환."""
    from PIL import Image
    from core.ocr_engine import OCREngine
    from utils.config import get_api_key

    png = Path(OCR_CACHE_ROOT) / stem / "crops_png" / f"crop_p{i}_c{ci}.png"
    if not png.exists():
        raise SystemExit(f"크롭 PNG 없음: {png} — 먼저 scripts/crop_dump.py 를 돌리세요.")
    # OCR eval 골든셋도 Sonnet 고정(자가발전 일관성 — 사용자 2026-06-16). 배포 GUI 만 Gemini.
    engine = _reocr.engine or OCREngine(api_key=get_api_key(), backend="claude")  # type: ignore[attr-defined]
    _reocr.engine = engine
    result = engine.recognize_crop(Image.open(png))  # raw(resolve_figs 미적용)
    eval_dir.mkdir(parents=True, exist_ok=True)
    (eval_dir / f"p{i}_c{ci}.json").write_text(
        json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result, engine


_reocr.engine = None  # type: ignore[attr-defined]


# ── A/B (baseline sig ↔ candidate sig) ──────────────────────────────────────────
# 두 프롬프트(보강 전/후) sig 의 eval 캐시 후보를 각각 골든과 채점해 비교한다. 재OCR 안 함
# (이미 캐시된 두 후보를 읽기만) → API 0원. 보강(core/ocr_reinforcement.md) 채택 게이트.
_AB_METRICS = ["text_ratio", "equation_ratio", "struct_score",
               "number_score", "score_score"]
_EPS = 1e-9


def _score_sig(stem, sig, goldens):
    """sig 의 eval 캐시 후보를 골든과 채점 → {sample_id: CropScore}, 누락 sample_id 목록."""
    eval_dir = Path(EVAL_ROOT) / stem / sig
    scores: dict = {}
    missing: list[str] = []
    for rec in goldens:
        src = rec.get("source", {})
        sid = rec.get("sample_id", "")
        cand = _candidate_from_cache(eval_dir, src.get("i"), src.get("ci"))
        if cand is None:
            missing.append(sid)
            continue
        scores[sid] = score_crop(cand, rec.get("golden", {}), sid)
    return scores, missing, eval_dir


def run_ab(stem, base_sig, cand_sig) -> int:
    """baseline↔candidate A/B. 집계 델타 + **문항별 회귀 목록**(평균에 묻히는 악화 노출) +
    게이트(PASS/FAIL) 출력. 반환 = 프로세스 종료코드(0 PASS / 1 FAIL)."""
    goldens = _load_golden_for_stem(stem)
    if not goldens:
        raise SystemExit(f"'{stem}' 골든이 tests/golden_ocr 에 없습니다.")

    base_scores, base_missing, base_dir = _score_sig(stem, base_sig, goldens)
    cand_scores, cand_missing, cand_dir = _score_sig(stem, cand_sig, goldens)
    if not base_dir.exists() or not cand_dir.exists():
        raise SystemExit(
            f"eval 캐시 없음: baseline={base_dir.exists()} candidate={cand_dir.exists()} "
            f"— score_ocr.py <PDF> --reocr 로 각 sig 후보를 먼저 생성하세요.")
    if not base_scores or not cand_scores:
        raise SystemExit("두 sig 모두에서 채점 가능한 후보가 없습니다(캐시 비어 있음).")

    base_agg = aggregate(list(base_scores.values()))
    cand_agg = aggregate(list(cand_scores.values()))

    print(f"A/B: baseline={base_sig} candidate={cand_sig} | golden={len(goldens)}")
    print(f"  baseline 후보 {len(base_scores)} / candidate 후보 {len(cand_scores)}")
    if base_missing or cand_missing:
        print(f"  ⚠️ 누락 — baseline:{len(base_missing)} candidate:{len(cand_missing)} "
              f"(공통 샘플만 문항별 비교)")

    print("── 집계 델타 (candidate − baseline) ──")
    for k in ("mean_text_ratio", "mean_equation_ratio", "struct_accuracy",
              "regression_rate"):
        b, c = base_agg.get(k), cand_agg.get(k)
        if isinstance(b, (int, float)) and isinstance(c, (int, float)):
            d = c - b
            arrow = "▲" if d > _EPS else ("▼" if d < -_EPS else "=")
            print(f"  {k:<22} {b:.4f} → {c:.4f}  ({d:+.4f}) {arrow}")

    # 문항별 회귀(평균에 묻히는 개별 악화를 반드시 드러낸다).
    common = sorted(set(base_scores) & set(cand_scores))
    regressed, improved = [], []
    for sid in common:
        b, c = base_scores[sid], cand_scores[sid]
        worse = [m for m in _AB_METRICS if getattr(c, m) + _EPS < getattr(b, m)]
        better = [m for m in _AB_METRICS if getattr(c, m) > getattr(b, m) + _EPS]
        new_regs = sorted(set(c.regressions) - set(b.regressions))
        if worse or new_regs:
            regressed.append((sid, worse, new_regs))
        elif better:
            improved.append((sid, better))

    print(f"── 문항별: 악화 {len(regressed)} / 개선 {len(improved)} (공통 {len(common)}) ──")
    for sid, worse, new_regs in regressed:
        tags = ", ".join(worse + [f"+{r}" for r in new_regs])
        print(f"  ✗ {sid}: {tags}")
    for sid, better in improved:
        print(f"  ✓ {sid}: {', '.join(better)}")

    # 게이트: 후보 회귀율이 baseline 이하 + 새로 악화된 문항 0.
    rate_ok = cand_agg["regression_rate"] <= base_agg["regression_rate"] + _EPS
    no_new_reg = len(regressed) == 0
    passed = rate_ok and no_new_reg
    print("── 게이트 ──")
    print(f"  회귀율 {cand_agg['regression_rate']:.4f} ≤ baseline "
          f"{base_agg['regression_rate']:.4f}: {'OK' if rate_ok else 'FAIL'}")
    print(f"  신규 악화 문항 없음: {'OK' if no_new_reg else f'FAIL({len(regressed)})'}")
    print(f"  >>> {'PASS — 채택 가능' if passed else 'FAIL — 되돌리거나 보강 재정련'}")
    return 0 if passed else 1


def main(argv):
    positional = [a for a in argv if not a.startswith("--")]

    # A/B 모드: --baseline=<sig> --candidate=<sig> (재OCR 없이 두 캐시 비교).
    base_sig = cand_sig = None
    for a in argv:
        if a.startswith("--baseline="):
            base_sig = a.split("=", 1)[1].strip()
        elif a.startswith("--candidate="):
            cand_sig = a.split("=", 1)[1].strip()
    if base_sig or cand_sig:
        if not (base_sig and cand_sig and positional):
            raise SystemExit("사용법: python scripts/ocr_eval/score_ocr.py <PDF> "
                             "--baseline=<sig> --candidate=<sig>")
        stem = os.path.splitext(os.path.basename(positional[0]))[0]
        raise SystemExit(run_ab(stem, base_sig, cand_sig))

    if not positional:
        raise SystemExit("사용법: python scripts/ocr_eval/score_ocr.py <PDF> [--reocr|--reocr=N,..]")
    pdf = positional[0]
    stem = os.path.splitext(os.path.basename(pdf))[0]

    reocr_all = "--reocr" in argv
    reocr_q = None
    for a in argv:
        if a.startswith("--reocr="):
            reocr_q = set(int(x) for x in a.split("=", 1)[1].split(",") if x.strip())

    sig = prompt_signature()
    eval_dir = Path(EVAL_ROOT) / stem / sig
    eval_dir.mkdir(parents=True, exist_ok=True)
    meta = prompt_metadata()
    meta.update({"created_at": datetime.now(timezone.utc).isoformat(), "pdf_stem": stem})
    (eval_dir / "metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    goldens = _load_golden_for_stem(stem)
    if not goldens:
        raise SystemExit(f"'{stem}' 에 대한 골든이 tests/golden_ocr 에 없습니다 — "
                         f"golden_record.py 로 먼저 시딩하세요.")
    print(f"prompt_sig={sig} | golden={len(goldens)} | eval={eval_dir}")

    scores = []
    n_api = n_cache = 0
    for rec in goldens:
        src = rec.get("source", {})
        i, ci = src.get("i"), src.get("ci")
        num = (rec.get("golden", {}).get("questions") or [{}])[0].get("number")
        want_reocr = reocr_all or (reocr_q is not None and num in reocr_q)
        cand = None if want_reocr else _candidate_from_cache(eval_dir, i, ci)
        if cand is None:
            cand, _ = _reocr(stem, i, ci, eval_dir)
            n_api += 1
        else:
            n_cache += 1
        scores.append(score_crop(cand, rec.get("golden", {}), rec.get("sample_id", "")))

    # scores.jsonl + summary.csv
    with open(eval_dir / "scores.jsonl", "w", encoding="utf-8") as f:
        for s in scores:
            f.write(json.dumps(asdict(s), ensure_ascii=False) + "\n")
    fields = list(asdict(scores[0]).keys())
    with open(eval_dir / "summary.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for s in scores:
            row = asdict(s)
            row["regressions"] = ";".join(row["regressions"])
            w.writerow(row)

    agg = aggregate(scores)
    print(f"OCR: {n_cache} cache, {n_api} api-call")
    print("── aggregate ──")
    for k, v in agg.items():
        print(f"  {k}: {v}")
    if _reocr.engine is not None:  # type: ignore[attr-defined]
        print("usage:", _reocr.engine.usage)  # type: ignore[attr-defined]
    print(f"wrote: {eval_dir/'scores.jsonl'} , {eval_dir/'summary.csv'}")


if __name__ == "__main__":
    main(sys.argv[1:])
