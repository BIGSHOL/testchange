# 골든 기록기 — 사람이 교정한 OCR JSON 을 검증해 tests/golden_ocr/<sample_id>.json 으로 기록.
#
# 사용법:
#   python scripts/ocr_eval/golden_record.py \
#       --manifest .testkit/ocr_cache/<stem>/crops_manifest.json \
#       --sample-id <stem>__p0__c2 \
#       --golden-json <작성한.json> [--overwrite]
#   (또는 --manifest 대신 --png <크롭PNG> 직접 지정 — sha256 만 계산, manifest 대조 생략)
#
# 검증(엄격): sample_id 가 manifest 에 있는가 / PNG 존재 / sha256 일치 / golden 스키마 통과 /
# 대상 파일이 이미 있으면 --overwrite 없이 실패. (채점기는 방어적, 시딩은 엄격 — 역할 분리.)
import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

GOLDEN_DIR = REPO / "tests" / "golden_ocr"
SCHEMA_VERSION = 1


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _validate_golden(golden: dict) -> None:
    """golden 본문이 OCR 스키마를 통과하는지 — ocr_engine.validate_ocr_response 재사용."""
    if not isinstance(golden, dict) or "questions" not in golden:
        raise SystemExit("golden 에 'questions' 키가 없습니다(스키마: {header, questions:[...]}).")
    from core.ocr_engine import validate_ocr_response
    q = validate_ocr_response(golden)
    if not q.valid:
        raise SystemExit(f"golden 스키마 검증 실패: {q.warnings}")
    if q.warnings:
        print("⚠️ 경고(기록은 진행):")
        for w in q.warnings:
            print("  -", w)
    # figure 안내문 오작성 방지: type==text 인데 '※ 그림 자리' 로 시작하면 거부.
    def _scan(blocks):
        for b in blocks or []:
            if isinstance(b, dict) and b.get("type") == "text" \
                    and str(b.get("value", "")).lstrip().startswith("※ 그림 자리"):
                raise SystemExit("golden 에 그림 안내문 text 가 있습니다 — figure 는 "
                                 "type=='figure' 블록으로 작성하세요(README 참고).")
    for ques in golden.get("questions") or []:
        if isinstance(ques, dict):
            _scan(ques.get("contents"))


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample-id", required=True)
    ap.add_argument("--golden-json", required=True, help="사람이 작성한 정답 JSON 경로")
    ap.add_argument("--manifest", help="crops_manifest.json (sha256·bbox 대조)")
    ap.add_argument("--png", help="크롭 PNG 직접 지정(manifest 없이 sha256만)")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args(argv)

    sample_id = args.sample_id
    golden_body = json.loads(Path(args.golden_json).read_text(encoding="utf-8"))
    # 사용자가 {header,questions} 만 줬으면 그대로, {golden:{...}} 로 감싼 것도 허용.
    golden = golden_body.get("golden", golden_body) if isinstance(golden_body, dict) else golden_body
    _validate_golden(golden)

    source: dict = {}
    png_sha256 = ""
    if args.manifest:
        man = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        samples = man.get("samples", {})
        if sample_id not in samples:
            raise SystemExit(f"sample_id '{sample_id}' 가 manifest 에 없습니다. "
                             f"(있는 것: {list(samples)[:5]}…)")
        entry = samples[sample_id]
        png_path = Path(args.manifest).parent / entry["png"]
        if not png_path.exists():
            raise SystemExit(f"PNG 가 없습니다: {png_path}")
        actual = _sha256(png_path)
        if actual != entry["sha256"]:
            raise SystemExit(f"PNG sha256 불일치 — manifest={entry['sha256'][:12]} "
                             f"actual={actual[:12]} (크롭이 바뀌었거나 재덤프 필요)")
        png_sha256 = actual
        source = {"pdf_stem": man.get("pdf_stem"), "i": entry["i"], "ci": entry["ci"],
                  "bbox": entry.get("bbox")}
    elif args.png:
        png_path = Path(args.png)
        if not png_path.exists():
            raise SystemExit(f"PNG 가 없습니다: {png_path}")
        png_sha256 = _sha256(png_path)
    else:
        raise SystemExit("--manifest 또는 --png 중 하나는 필요합니다.")

    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    out_fp = GOLDEN_DIR / f"{sample_id}.json"
    if out_fp.exists() and not args.overwrite:
        raise SystemExit(f"이미 존재: {out_fp} (덮어쓰려면 --overwrite)")

    record = {
        "schema_version": SCHEMA_VERSION,
        "sample_id": sample_id,
        "png_sha256": png_sha256,
        "source": source,
        "golden": golden,
    }
    out_fp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"기록: {out_fp}")


if __name__ == "__main__":
    main(sys.argv[1:])
