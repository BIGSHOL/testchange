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
    engine = _reocr.engine or OCREngine(api_key=get_api_key())  # type: ignore[attr-defined]
    _reocr.engine = engine
    result = engine.recognize_crop(Image.open(png))  # raw(resolve_figs 미적용)
    eval_dir.mkdir(parents=True, exist_ok=True)
    (eval_dir / f"p{i}_c{ci}.json").write_text(
        json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result, engine


_reocr.engine = None  # type: ignore[attr-defined]


def main(argv):
    positional = [a for a in argv if not a.startswith("--")]
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
