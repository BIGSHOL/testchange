"""문제 내 수학 그림 재생성: Claude 비전 → 깨끗한 인라인 SVG → resvg_py → PNG.

파이프라인은 그림 크롭 픽셀을 Claude 에 직접 보여주고(math-gen 스타일 SVG 규칙)
교과서급 SVG 로 재현한다. 벡터화 불가(사진·인물·역사적 그림)거나 신뢰도가 낮으면
원본 크롭을 그대로 PNG 로 저장(폴백)한다.

설계 메모: figure-svg-generation. PoC: D:\\tmp\\poc_svg.py.
"""

from __future__ import annotations

import json
import logging
import os
import re

from PIL import Image

from core.pdf_handler import image_to_base64
from utils.config import get_api_key, CLAUDE_MODEL

logger = logging.getLogger(__name__)

# 재생성 채택 임계값(이 미만이면 크롭 폴백). 수학 시험이라 보수적으로 시작.
CONFIDENCE_THRESHOLD = 0.75
# 그림 생성 모델(기본=OCR과 동일 sonnet, PoC 검증). config 의 CLAUDE_MODEL 사용.
FIGURE_MODEL = CLAUDE_MODEL
# 크롭 폴백 PNG 의 가로 폭 상한(HWP 표시 과대화 방지) — 기존 _save_figure_crop 과 동일.
RASTER_TARGET_W = 420
# 재생성 SVG → PNG 렌더 가로 폭(px). insert_picture 는 원본 픽셀 크기로 삽입하므로
# 크롭 폴백과 동일 폭(420)으로 맞춰 표시 크기 일관성 확보(과대 렌더 방지).
SVG_RENDER_W = 420

# math-gen 스타일 SVG 규칙(PoC 에서 교과서급 검증). 비전 입력이므로 "재현"에 초점.
SVG_RULES = """You redraw a Korean math-exam figure as ONE clean inline SVG, faithfully \
reproducing the math content of the image you are given (a cropped figure).

Reproduce the math content faithfully: same axes, same labeled points, same values, \
same open/closed points, same labels. Do NOT invent or omit values.

GEOMETRIC IDEALIZATION (critical): hand-drawn/scanned figures are often sloppy. Draw the
figure as it is MATHEMATICALLY DEFINED, not pixel-faithful to a loose sketch. Use the
figure type (from the description/labels) to draw the correct ideal shape:
- 정육면체(cube) 전개도 / cube net → exactly SIX CONGRUENT SQUARES on a fixed grid.
  Choose a cell size S (e.g. 70) and snap EVERY face to the grid: face at column i, row j
  occupies the square (x0 + i*S, y0 + j*S, width S, height S). ALL six faces use the SAME
  S for width AND height. ⚠️ Scanned cube nets almost always look like the vertical column
  is NARROWER than the horizontal row — that is SCANNER DISTORTION, an artifact, NOT real.
  IGNORE the apparent widths entirely; take ONLY the grid arrangement (which label sits in
  which grid cell) from the image, and draw every cell as the identical square S×S. Center
  each label in its cell.
- 정사각형=square, 정삼각형/정n각형=regular polygon, 원=true circle, 직육면체 faces=rectangles.
- Parallel lines parallel, right angles square, equal-length sides equal.
BUT preserve differences the problem treats as MEANINGFUL: graph point positions and
values exactly; and when the figure compares two objects by size (e.g. one solid taller
than another), keep that difference. Idealize the SHAPE, preserve the DATA.

SVG rules (critical):
- viewBox like "0 0 400 300", transparent background. Strokes black #000:
  main lines 2px, axes/auxiliary 1px.
- Curves: a single smooth <path> with C/Q bezier. NEVER approximate a curve with
  <polyline> or many <line> segments (jagged = fail).
- NO LaTeX/MathML inside the SVG. Labels via <text>. Fractions as vertical pure-SVG
  (numerator <text>, bar <line>, denominator <text>).
- Filled point = filled circle; open point = stroked circle with white fill.
- Keep it textbook-clean and minimal.

vectorizable=true for ANY line-art math figure — number lines, coordinate planes,
function/curve graphs, geometric shapes (triangles, circles, polygons, 3D solids),
statistical charts (bar/histogram/line/pie), tree/Venn diagrams, tables of figures.
These are ALWAYS vectorizable even if the crop is a thin strip, sparse, or low-res —
reproduce them. confidence reflects how faithfully you can reproduce the VALUES, not
whether to attempt it.
Set vectorizable=false ONLY for true raster content: a photograph, a person/portrait,
a historical artwork/painting, or a real-world scene. Then output no SVG.

CRITICAL — do NOT guess missing parts. If the figure looks CUT OFF / clipped by the
image edges (a shape running off the top/side, an axis or label partially outside),
you cannot faithfully reproduce it: set confidence <= 0.3 and do not invent the missing
geometry. Preserve real differences between figures (e.g. one box taller than another) —
never normalize two different figures into identical ones.

Respond in EXACTLY this format, nothing else (no markdown fences, no commentary):
1) First line — one JSON object: {"vectorizable": true|false, "confidence": 0.0-1.0}
   confidence = how sure you are the SVG faithfully reproduces the original values.
2) Then, only if vectorizable is true:
   a) a <desc>...</desc> block that TRANSCRIBES the figure precisely BEFORE drawing —
      figure type, axis ranges and EVERY tick label, every plotted point with its
      coordinate and state (open/closed), every labeled value. Read carefully.
   b) then the SVG element <svg ...> ... </svg> that reproduces exactly that <desc>.
This read-then-draw order is mandatory: never emit an SVG without first transcribing.
"""


def _flatten_white(image: Image.Image) -> Image.Image:
    """투명/팔레트 이미지를 흰 배경 위에 합성해 RGB 로 평탄화.

    크롭에 알파가 있으면 RGB 변환 시 투명→검정으로 합성되어 검은선이 보이지 않게
    되므로(비전·HWP 모두 오작동) 반드시 흰 배경으로 평탄화한다.
    """
    if image.mode == "RGB":
        return image
    try:
        rgba = image.convert("RGBA")
        bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        return Image.alpha_composite(bg, rgba).convert("RGB")
    except Exception:  # noqa: BLE001
        return image.convert("RGB")


def _save_raster(image: Image.Image, path: str, target_w: int = RASTER_TARGET_W) -> str | None:
    """원본 크롭을 PNG 로 저장(가로 폭 상한 리사이즈). 경로 반환, 실패 시 None.

    기존 gui.main_window._save_figure_crop 의 리사이즈 로직을 이관.
    """
    try:
        crop = image
        if crop.width > target_w:
            crop = crop.resize(
                (target_w, int(crop.height * target_w / crop.width)),
                Image.LANCZOS,
            )
        crop.save(path)
        return path
    except Exception as e:  # noqa: BLE001
        logger.warning("크롭 PNG 저장 실패: %s", e)
        return None


def _svg_to_png_bytes(svg: str, width: int = SVG_RENDER_W) -> bytes | None:
    """SVG 문자열 → PNG bytes(resvg_py). 실패 시 None.

    resvg 는 주석 안 '--' 를 거부하므로 주석을 제거한다. 일부 빌드는 list[int] 를
    반환하므로 bytes 로 정규화.
    """
    try:
        import resvg_py
    except Exception as e:  # noqa: BLE001
        logger.warning("resvg_py import 실패 — 크롭 폴백: %s", e)
        return None
    svg = re.sub(r"<!--.*?-->", "", svg, flags=re.S)  # resvg: 주석 '--' 거부
    try:
        png = resvg_py.svg_to_bytes(svg_string=svg, width=width)
        if isinstance(png, list):
            png = bytes(png)
        if not png:
            return None
        return png
    except Exception as e:  # noqa: BLE001
        logger.warning("SVG 렌더 실패 — 크롭 폴백: %s", e)
        return None


def _vision_to_svg(image: Image.Image, hint: str, api_key: str | None) -> dict:
    """크롭 이미지를 Claude 비전에 보여주고 SVG 재현을 요청.

    반환: {"vectorizable": bool, "confidence": float, "svg": str}
    호출/파싱 실패 시 vectorizable=False.
    """
    import anthropic

    out = {"vectorizable": False, "confidence": 0.0, "svg": ""}
    try:
        # 병렬 그림 재생성(_resolve_figures) 버스트의 429/5xx 를 SDK 백오프로 흡수.
        client = anthropic.Anthropic(api_key=api_key or get_api_key(), max_retries=5)
        b64 = image_to_base64(image, format="PNG")
        user_text = "이 크롭 그림을 위 규칙대로 재현하세요."
        if hint:
            user_text += f"\n참고 설명(부정확할 수 있음): {hint}"
        msg = client.messages.create(
            model=FIGURE_MODEL,
            max_tokens=4000,
            system=SVG_RULES,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64",
                                                 "media_type": "image/png", "data": b64}},
                    {"type": "text", "text": user_text},
                ],
            }],
        )
        text = msg.content[0].text
    except Exception as e:  # noqa: BLE001
        logger.warning("그림 비전 호출 실패 — 크롭 폴백: %s", e)
        return out

    # 1) 메타 JSON(첫 줄 한 객체) 추출
    mm = re.search(r'\{[^{}]*"vectorizable"[^{}]*\}', text)
    if mm:
        try:
            meta = json.loads(mm.group(0))
            out["vectorizable"] = bool(meta.get("vectorizable", False))
            out["confidence"] = float(meta.get("confidence", 0.0) or 0.0)
        except Exception:  # noqa: BLE001
            pass
    # 2) SVG 추출
    ms = re.search(r"<svg.*?</svg>", text, re.S)
    if ms:
        out["svg"] = ms.group(0)
    return out


def render_figure(
    image: Image.Image,
    hint: str,
    out_dir: str,
    basename: str,
    api_key: str | None = None,
) -> tuple[str | None, str]:
    """그림 크롭을 재생성(또는 폴백)해 PNG 로 저장.

    Args:
        image: 그림 크롭 PIL 이미지.
        hint: OCR 이 준 짧은 설명(부정확 가능). "[photo]" 접두면 사진 힌트.
        out_dir: PNG 저장 디렉터리.
        basename: 확장자 없는 파일명(예 "fig_p1_2").
        api_key: Claude API 키(없으면 config).

    Returns:
        (png_path, mode). mode ∈ {"svg","crop","none"}. 둘 다 실패 시 (None,"none").
    """
    os.makedirs(out_dir, exist_ok=True)
    png_path = os.path.join(out_dir, f"{basename}.png")
    image = _flatten_white(image)  # 알파→흰배경(검은선 보존), 이후 비전·크롭 공통

    # 사진 힌트면 비전 호출 없이 곧장 크롭(비용/지연 절약). 그 외엔 재생성 시도.
    photo_hint = hint.strip().lower().startswith("[photo]") if hint else False
    if not photo_hint:
        res = _vision_to_svg(image, hint, api_key)
        if (res["vectorizable"] and res["confidence"] >= CONFIDENCE_THRESHOLD
                and res["svg"]):
            png = _svg_to_png_bytes(res["svg"])
            if png:
                try:
                    # resvg 출력은 투명 배경 → 흰 배경으로 평탄화(소비처에서 검정화 방지)
                    import io as _io
                    _im = _flatten_white(Image.open(_io.BytesIO(png)))
                    _buf = _io.BytesIO(); _im.save(_buf, format="PNG"); png = _buf.getvalue()
                    with open(png_path, "wb") as f:
                        f.write(png)
                    logger.info("그림 재생성 성공(conf=%.2f): %s", res["confidence"], basename)
                    return png_path, "svg"
                except Exception as e:  # noqa: BLE001
                    logger.warning("재생성 PNG 저장 실패 — 크롭 폴백: %s", e)
            else:
                logger.info("SVG 렌더 실패 → 크롭 폴백: %s", basename)
        else:
            logger.info("재생성 미채택(vec=%s conf=%.2f) → 크롭 폴백: %s",
                        res["vectorizable"], res["confidence"], basename)

    # 폴백: 원본 크롭 raster
    p = _save_raster(image, png_path)
    if p:
        return p, "crop"
    return None, "none"
