# -*- coding: utf-8 -*-
"""세션 변환 렌더 하네스 — corpus OCR JSON + SVG 작도 그림 → 대수회 폼(.hwp).

⚠️ 세션 변환이므로 **OCR 엔진을 인스턴스화하지 않는다**(CLAUDE.md 구독요금제 규약).
그림은 `fig_svgs.py` 가 그린 SVG→PNG 를 문항 번호로 이어 붙여 COM 이 실제로 삽입한다
(그래야 폼 슬롯 높이 측정에 그림 높이가 반영된다 — 토큰만 넣고 나중에 끼우면 단 배치가
어긋난다). 삽입 크기는 **mm 지정**(sizeoption=1) — HWP 는 PNG 의 dpi 메타를 무시하고
96dpi 로 읽으므로(실측 2026-08-15), 고해상도 PNG 를 원래 크기로 넣으면 지면을 넘는다.
"""
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile

from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from PIL import Image                                        # noqa: E402
import core.hwp_form_writer as hfw                           # noqa: E402
from core.content_parser import parse_ocr_response, build_document   # noqa: E402
from core.form_registry import parse_filename, resolve_form  # noqa: E402
from core.hwp_form_writer import write_exam_to_form          # noqa: E402

# 문항번호 → (그림 키, 삽입 폭 mm). 폼 단 너비는 B4 기준 약 104mm.
FIG_MAP = {4: ("q4", 60.0), 12: ("q12", 54.0), 14: ("q14", 60.0), 16: ("q16", 60.0)}
PNG_DIR = Path(tempfile.gettempdir()) / "exam_figure_svg" / "daejin_gs2_final"


def build_figures():
    """fig_svgs.py 를 실행해 검산·lint 를 통과한 PNG 를 만든다(실패 시 중단)."""
    import subprocess
    r = subprocess.run([sys.executable, str(HERE / "fig_svgs.py")],
                       capture_output=True, text=True, encoding="utf-8")
    print(r.stdout.strip())
    if r.returncode != 0:
        print(r.stderr.strip())
        raise SystemExit("그림 작도 실패 — 렌더 중단")
    return {k: str(PNG_DIR / f"{k}.png") for k in ("q4", "q12", "q14", "q16")}


def flatten_white(path):
    """투명 배경 → 흰 배경 RGB(검정화 방지). 해상도는 그대로 유지한다."""
    out = os.path.join(tempfile.gettempdir(), "djfig_" + os.path.basename(path))
    with Image.open(path) as im0:
        rgba = im0.convert("RGBA")
        bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        Image.alpha_composite(bg, rgba).convert("RGB").save(out)
    return out


_WIDTH_MM = {}


def _place_figure_embed_mm(ses, h, path, max_w=hfw.FORM_FIG_MAX_W):
    """그림 삽입 — 토큰 + **mm 지정 크기** InsertPicture(고해상도 유지)."""
    if not path or not os.path.exists(path):
        return False
    paths = getattr(ses, "_fig_paths", None)
    if paths is None:
        paths = []
        ses._fig_paths = paths
    idx = len(paths)
    paths.append(path)                       # 삽입 파일 == 임베드 파일(orgSz 일치)
    try:
        ses.text(hfw._fig_token(idx))
    except Exception:                        # noqa: BLE001
        pass
    w_mm = _WIDTH_MM.get(os.path.abspath(path), 54.0)
    with Image.open(path) as im:
        px_w, px_h = im.size
    h_mm = round(w_mm * px_h / px_w, 2)
    try:
        h.InsertPicture(path, True, 1, 0, 0, 0, w_mm, h_mm)
    except Exception:                        # noqa: BLE001
        h.InsertPicture(path, True, 2)
    try:
        h.Run("MoveRight")
    except Exception:                        # noqa: BLE001
        pass
    return True


def load_pages(fig_paths):
    files = sorted((HERE / "ocr").iterdir(),
                   key=lambda p: int(re.search(r"p(\d+)_merged", p.name).group(1)))
    pages = []
    used = []
    for pnum, fp in enumerate([f for f in files if re.match(r"p\d+_merged\.json$", f.name)], 1):
        d = json.load(open(fp, encoding="utf-8"))
        for q in d.get("questions") or []:
            key = FIG_MAP.get(q.get("number"))
            blocks = q.get("contents") or []
            for i, b in enumerate(blocks):
                if isinstance(b, dict) and b.get("type") == "figure":
                    if not key:
                        raise SystemExit(f"그림 매핑 없음: Q{q.get('number')}")
                    name, mm = key
                    p = flatten_white(fig_paths[name])
                    _WIDTH_MM[os.path.abspath(p)] = mm
                    blocks[i] = {"type": "image", "value": p}
                    used.append((q.get("number"), name, mm))
        pages.append(parse_ocr_response(d, page_number=pnum))
    print("그림 삽입:", ", ".join(f"Q{n}={k}({mm}mm)" for n, k, mm in used))
    return pages


def main(argv):
    out = os.path.abspath(argv[0]) if argv else str(HERE / "out" / "대진고_공수2_기말_변환.hwp")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    figs = build_figures()
    hfw._place_figure_embed = _place_figure_embed_mm      # 그림 삽입 방식 교체
    pages = load_pages(figs)
    doc = build_document(pages)
    print(f"문항 {sum(len(p.questions) for p in pages)}개, 배점합 "
          f"{sum(q.score or 0 for p in pages for q in p.questions):.1f}")
    info = parse_filename(HERE.name)
    form = resolve_form(HERE.name)
    if not form:
        raise SystemExit(f"폼 매칭 실패: {HERE.name}")
    print("폼:", os.path.basename(form))
    res = write_exam_to_form(doc, form, out,
                             header_values=(info if info["valid"] else None),
                             render_figures=True)
    print("WROTE:", res, os.path.exists(res), os.path.getsize(res), "bytes")


if __name__ == "__main__":
    main(sys.argv[1:])
