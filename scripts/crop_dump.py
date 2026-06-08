# 골든셋 입력층 — 크롭 PNG 덤프 + manifest. (플라이휠 1단계, docs/HANDOFF.md 참고.)
#
# Gemini 크롭검출(캐시 재사용) → 각 비-figure 박스를 PNG 로 잘라 저장 + crops_manifest.json.
# 이 PNG 를 사람이 보고 정답 JSON 을 작성, golden_record.py 로 tests/golden_ocr/ 에 기록한다.
#
# 사용법:
#   python scripts/crop_dump.py <PDF>          # crops.json 있으면 재사용, 없으면 Gemini 1회
#   python scripts/crop_dump.py <PDF> --recrop # 크롭검출 다시(Gemini 재호출)
#
# 인덱스(i,ci)는 scripts/testkit.py 캐시 파일명과 **동일** 규칙:
#   i  = 0-based 페이지 인덱스(박스 없는 페이지 포함, enumerate(cropsets))
#   ci = 그 페이지의 **비-figure** 박스 순번
# → eval 후보 캐시(p{i}_c{ci}.json)·골든 source 와 정합.
import hashlib
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from core.pdf_handler import pdf_to_images
from core.crop_detector import detect_crops, CropBox
from utils.config import get_api_key

_TESTKIT_DIR = REPO / ".testkit"
CACHE_ROOT = os.environ.get("TESTKIT_CACHE", str(_TESTKIT_DIR / "ocr_cache"))
MANIFEST_SCHEMA_VERSION = 1


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv):
    positional = [a for a in argv if not a.startswith("--")]
    if not positional:
        raise SystemExit("사용법: python scripts/crop_dump.py <PDF> [--recrop]")
    pdf = positional[0]
    recrop = "--recrop" in argv

    stem = os.path.splitext(os.path.basename(pdf))[0]
    cache_dir = os.path.join(CACHE_ROOT, stem)
    png_dir = os.path.join(cache_dir, "crops_png")
    os.makedirs(png_dir, exist_ok=True)
    crops_fp = os.path.join(cache_dir, "crops.json")
    manifest_fp = os.path.join(cache_dir, "crops_manifest.json")

    api = get_api_key()
    imgs = pdf_to_images(pdf)
    print(f"loaded {len(imgs)} pages | cache: {cache_dir}")

    # 크롭 검출(testkit 와 동일 캐시 재사용)
    if os.path.exists(crops_fp) and not recrop:
        raw = json.load(open(crops_fp, encoding="utf-8"))
        cropsets = [[CropBox(**b) for b in page] for page in raw]
        print("crops: CACHE")
    else:
        cropsets = [None] * len(imgs)
        with ThreadPoolExecutor(max_workers=6) as ex:
            futs = {ex.submit(detect_crops, imgs[i], api): i for i in range(len(imgs))}
            for f in as_completed(futs):
                i = futs[f]
                try:
                    cropsets[i] = f.result()
                except Exception as e:  # noqa: BLE001
                    print(f"crop p{i+1} fail: {e}")
                    cropsets[i] = []
        json.dump([[asdict(b) for b in (page or [])] for page in cropsets],
                  open(crops_fp, "w", encoding="utf-8"), ensure_ascii=False)
        print("crops: Gemini → cached")

    samples: dict[str, dict] = {}
    n_png = 0
    for i, boxes in enumerate(cropsets):
        boxes = [b for b in (boxes or []) if getattr(b, "kind", "") != "figure"]
        for ci, box in enumerate(boxes):
            sample_id = f"{stem}__p{i}__c{ci}"
            png_name = f"crop_p{i}_c{ci}.png"
            png_path = os.path.join(png_dir, png_name)
            sub = box.crop_image(imgs[i], pad=0.01)
            sub.save(png_path, "PNG")
            n_png += 1
            samples[sample_id] = {
                "i": i,
                "ci": ci,
                "png": os.path.join("crops_png", png_name),
                "sha256": _sha256(png_path),
                "bbox": [box.x0, box.y0, box.x1, box.y1],
                "number": box.number,
                "qtype": getattr(box, "qtype", ""),
            }

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "pdf_stem": stem,
        "samples": samples,
    }
    json.dump(manifest, open(manifest_fp, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"dumped {n_png} crop PNGs → {png_dir}")
    print(f"manifest: {manifest_fp} ({len(samples)} samples)")


if __name__ == "__main__":
    main(sys.argv[1:])
