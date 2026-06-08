# Supabase 동기화 — 골든·런·점수·크롭 PNG push (개발/수동 전용).
#
# 사용법:
#   python scripts/ocr_eval/supabase_sync.py <PDF> [--dry-run]
#     --dry-run : 무엇을 push 할지만 출력(실제 네트워크 호출 없음 — 멱등/RLS 차단 확인용).
#
# 키: config.json 의 SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY (gitignore, 절대 커밋 금지).
#     키가 없으면 즉시 스킵. `supabase` 패키지는 lazy import(배포 exe 비포함, requirements-dev).
#
# 멱등: 골든=sample_id upsert, 크롭 PNG=Storage crops/<sha256>.png(같은 sha256 재업로드 스킵).
import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from utils.config import get_supabase

_TESTKIT_DIR = REPO / ".testkit"
OCR_CACHE_ROOT = os.environ.get("TESTKIT_CACHE", str(_TESTKIT_DIR / "ocr_cache"))
EVAL_ROOT = str(_TESTKIT_DIR / "ocr_eval")
GOLDEN_DIR = REPO / "tests" / "golden_ocr"


def _client():
    """supabase 클라이언트(lazy import). 미설치면 친절한 안내."""
    try:
        from supabase import create_client
    except ImportError:
        raise SystemExit("`supabase` 패키지가 없습니다 — `pip install -r requirements-dev.txt`")
    creds = get_supabase()
    if not creds:
        raise SystemExit("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY 미설정(config.json) — 스킵.")
    url, key = creds
    return create_client(url, key)


def _load_goldens(stem: str) -> list[dict]:
    out = []
    for fp in sorted(GOLDEN_DIR.glob("*.json")):
        try:
            rec = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if rec.get("source", {}).get("pdf_stem") == stem:
            out.append(rec)
    return out


def _latest_eval(stem: str) -> Path | None:
    base = Path(EVAL_ROOT) / stem
    if not base.exists():
        return None
    dirs = sorted([d for d in base.iterdir() if d.is_dir()],
                  key=lambda d: d.stat().st_mtime, reverse=True)
    return dirs[0] if dirs else None


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    stem = os.path.splitext(os.path.basename(args.pdf))[0]

    goldens = _load_goldens(stem)
    eval_dir = _latest_eval(stem)
    meta = json.loads((eval_dir / "metadata.json").read_text(encoding="utf-8")) \
        if eval_dir and (eval_dir / "metadata.json").exists() else None
    scores = []
    if eval_dir and (eval_dir / "scores.jsonl").exists():
        scores = [json.loads(line) for line in
                  (eval_dir / "scores.jsonl").read_text(encoding="utf-8").splitlines() if line]

    plan = {
        "prompt_versions": 1 if meta else 0,
        "golden_samples (upsert)": len(goldens),
        "crops (Storage, sha256 멱등)": len(goldens),
        "ocr_runs": 1 if scores else 0,
        "scores": len(scores),
    }
    if args.dry_run:
        print(f"[dry-run] stem={stem} | sig={meta and meta.get('prompt_sig')}")
        for k, v in plan.items():
            print(f"  would push {k}: {v}")
        creds = get_supabase()
        print("  creds:", "set" if creds else "MISSING(스킵)")
        print("  RLS: 정책 미생성 → service_role 키로만 접근(anon 차단). schema.sql 참고.")
        return

    sb = _client()  # 키 없으면 여기서 SystemExit
    # prompt_versions upsert
    if meta:
        sb.table("prompt_versions").upsert({
            "sig": meta["prompt_sig"], "prompt_sha256": meta["prompt_sha256"],
            "model": meta["model"], "runner": meta["runner"],
            "schema_version": meta["schema_version"],
        }).execute()
    # golden_samples upsert + 크롭 PNG Storage(sha256 멱등)
    for rec in goldens:
        src = rec.get("source", {})
        sb.table("golden_samples").upsert({
            "sample_id": rec["sample_id"], "pdf_stem": src.get("pdf_stem"),
            "page_i": src.get("i"), "crop_ci": src.get("ci"), "bbox": src.get("bbox"),
            "png_sha256": rec.get("png_sha256"), "golden": rec.get("golden"),
        }).execute()
        _upload_crop(sb, stem, rec)
    # ocr_runs + scores
    if scores and meta:
        run = sb.table("ocr_runs").insert({
            "sig": meta["prompt_sig"], "pdf_stem": stem,
            "aggregate": _read_aggregate(eval_dir),
        }).execute()
        run_id = run.data[0]["id"]
        for s in scores:
            sb.table("scores").insert({
                "run_id": run_id, "sample_id": s.get("sample_id"), "score": s,
            }).execute()
    print(f"pushed: {plan}")


def _read_aggregate(eval_dir: Path) -> dict:
    # summary 는 크롭별이라 aggregate 는 재계산(scores.jsonl 로). 가벼우니 여기서.
    from dataclasses import fields
    from scripts.ocr_eval.metrics import CropScore, aggregate
    rows = [json.loads(line) for line in
            (eval_dir / "scores.jsonl").read_text(encoding="utf-8").splitlines() if line]
    valid = {f.name for f in fields(CropScore)}
    objs = [CropScore(**{k: v for k, v in r.items() if k in valid}) for r in rows]
    return aggregate(objs)


def _upload_crop(sb, stem: str, rec: dict) -> None:
    sha = rec.get("png_sha256")
    if not sha:
        return
    png = Path(OCR_CACHE_ROOT) / stem / "crops_png" / \
        f"crop_p{rec['source']['i']}_c{rec['source']['ci']}.png"
    if not png.exists():
        return
    try:
        sb.storage.from_("crops").upload(
            f"{sha}.png", str(png), {"content-type": "image/png", "upsert": "false"})
    except Exception:
        pass  # 이미 있으면(같은 sha256) 멱등 스킵


if __name__ == "__main__":
    main(sys.argv[1:])
