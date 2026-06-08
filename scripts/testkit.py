# OCR 캐시 기반 변환 테스트 키트 — 불필요한 API 비용 차단.
#
# 핵심: 크롭검출(Gemini)·OCR(Claude) 결과를 디스크에 캐시한다.
#   - 파서/렌더(content_parser·hwp_com_writer 등) 변경 검증 → 캐시 재사용, **API 0회**.
#   - 프롬프트/복구(ocr_engine) 변경 검증 → 해당 크롭만 --reocr 로 재OCR(타깃만 과금).
#
# 사용법:
#   python scripts/testkit.py <PDF> [OUT.hwpx]   # 캐시 사용(없는 것만 OCR), 변환+저장
#   python scripts/testkit.py <PDF> --render-only  # 캐시만 사용, API 절대 호출 안 함
#   python scripts/testkit.py <PDF> --reocr        # 모든 크롭 재OCR(프롬프트 전체 검증)
#   python scripts/testkit.py <PDF> --reocr=12,18  # 12·18번 문항 크롭만 재OCR
#   python scripts/testkit.py <PDF> --recrop       # 크롭검출도 다시(Gemini 재호출)
#
# 경로(환경변수로 덮어쓰기 가능):
#   TESTKIT_PDF    기본 PDF (positional 로 줘도 됨)
#   TESTKIT_OUT    출력 .hwpx (기본: <repo>/.testkit/testkit_out.hwpx)
#   TESTKIT_CACHE  OCR 캐시 루트 (기본: <repo>/.testkit/ocr_cache)
#                  → 다른 컴퓨터로 이어작업 시 이 폴더(<pdf_stem>/*.json)만 복사하면
#                    API 0원으로 동일 렌더 재현(캐시 = crops.json + ocr_p{p}_c{c}.json).
import sys, os, json
from dataclasses import asdict
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from core.pdf_handler import pdf_to_images
from core.crop_detector import detect_crops, CropBox
from core.ocr_engine import OCREngine
from core.content_parser import parse_ocr_response, build_document
from core.hwp_form_writer import write_exam_to_form
from core.form_registry import parse_filename, resolve_form
from utils.config import get_api_key

_TESTKIT_DIR = REPO / ".testkit"
DEF_PDF = os.environ.get("TESTKIT_PDF", "")
DEF_OUT = os.environ.get("TESTKIT_OUT", str(_TESTKIT_DIR / "testkit_out.hwpx"))
CACHE_ROOT = os.environ.get("TESTKIT_CACHE", str(_TESTKIT_DIR / "ocr_cache"))
FIG_NOTE = "※ 그림 자리 — 원본에서 이 영역을 캡처해 여기에 붙여넣으세요"


def resolve_figs(d):
    def fix(blocks):
        if not isinstance(blocks, list):
            return blocks
        return [{"type": "text", "value": FIG_NOTE}
                if isinstance(b, dict) and b.get("type") == "figure" else b
                for b in blocks]
    for q in d.get("questions") or []:
        if not isinstance(q, dict):
            continue
        if "contents" in q:
            q["contents"] = fix(q["contents"])
        for ch in q.get("choices") or []:
            if isinstance(ch, dict) and "contents" in ch:
                ch["contents"] = fix(ch["contents"])
        for sub in q.get("sub_questions") or []:
            if isinstance(sub, dict) and "contents" in sub:
                sub["contents"] = fix(sub["contents"])


def main(argv):
    pdf = DEF_PDF
    out = DEF_OUT
    render_only = "--render-only" in argv
    recrop = "--recrop" in argv
    reocr_all = "--reocr" in argv
    reocr_q = None
    for a in argv:
        if a.startswith("--reocr="):
            reocr_q = set(int(x) for x in a.split("=", 1)[1].split(",") if x.strip())
    positional = [a for a in argv if not a.startswith("--")]
    if len(positional) >= 1:
        pdf = positional[0]
    if len(positional) >= 2:
        out = positional[1]
    if not pdf:
        raise SystemExit("PDF 경로를 주세요: python scripts/testkit.py <PDF> "
                         "[OUT.hwpx] [--render-only|--reocr|--reocr=N|--recrop]")

    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    stem = os.path.splitext(os.path.basename(pdf))[0]
    cache_dir = os.path.join(CACHE_ROOT, stem)
    os.makedirs(cache_dir, exist_ok=True)
    crops_fp = os.path.join(cache_dir, "crops.json")

    def api_guard(what):
        if render_only:
            raise SystemExit(f"[render-only] {what} 캐시 없음 — API 호출 금지 모드. "
                             f"--reocr/--recrop 로 캐시를 먼저 만드세요.")

    api = get_api_key()
    imgs = pdf_to_images(pdf)
    print(f"loaded {len(imgs)} pages | cache: {cache_dir}")

    # ── 크롭 검출(캐시) ──
    if os.path.exists(crops_fp) and not recrop:
        raw = json.load(open(crops_fp, encoding="utf-8"))
        cropsets = [[CropBox(**b) for b in page] for page in raw]
        print("crops: CACHE")
    else:
        api_guard("crop detection")
        cropsets = [None] * len(imgs)
        with ThreadPoolExecutor(max_workers=6) as ex:
            futs = {ex.submit(detect_crops, imgs[i], api): i for i in range(len(imgs))}
            for f in as_completed(futs):
                i = futs[f]
                try:
                    cropsets[i] = f.result()
                except Exception as e:
                    print(f"crop p{i+1} fail: {e}"); cropsets[i] = []
        json.dump([[asdict(b) for b in (page or [])] for page in cropsets],
                  open(crops_fp, "w", encoding="utf-8"), ensure_ascii=False)
        print("crops: OCR(Gemini) → cached")

    engine = OCREngine(api_key=api)
    pages = []
    pnum = 0
    n_api = n_cache = 0
    for i, boxes in enumerate(cropsets):
        boxes = [b for b in (boxes or []) if getattr(b, "kind", "") != "figure"]
        if not boxes:
            continue
        pnum += 1
        merged = {"header": "", "questions": []}
        for ci, box in enumerate(boxes):
            ocr_fp = os.path.join(cache_dir, f"ocr_p{i}_c{ci}.json")
            want_reocr = reocr_all or (reocr_q is not None and box.number in reocr_q)
            if os.path.exists(ocr_fp) and not want_reocr:
                r = json.load(open(ocr_fp, encoding="utf-8")); n_cache += 1
            else:
                api_guard(f"OCR p{i} c{ci} (#{box.number})")
                sub = box.crop_image(imgs[i], pad=0.01)
                r = engine.recognize_crop(sub); n_api += 1
                resolve_figs(r)
                json.dump(r, open(ocr_fp, "w", encoding="utf-8"), ensure_ascii=False)
            qs = r.get("questions", [])
            if box.number is not None:
                for q in qs:
                    q["number"] = box.number
            merged["questions"].extend(qs)
        page = parse_ocr_response(merged, page_number=pnum)
        pages.append(page)
    print(f"OCR: {n_cache} cache, {n_api} api-call")

    doc = build_document(pages)
    info = parse_filename(pdf)
    form = resolve_form(pdf)
    res = write_exam_to_form(doc, form, out,
                             header_values=(info if info["valid"] else None),
                             render_figures=False)
    print("WROTE:", res, os.path.exists(res))


if __name__ == "__main__":
    main(sys.argv[1:])
