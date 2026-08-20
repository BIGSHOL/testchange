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
# 모델이 그린 SVG가 구조/픽셀 게이트에서 탈락했을 때, 진단을 돌려 한 번만 재작도한다.
# 무한 수정 루프와 API 비용 폭증을 막기 위해 2회(초안+교정)로 고정한다.
SVG_GENERATION_ATTEMPTS = 2
# OCR 설명은 보조 힌트일 뿐이며 모델 입력 비용/재시도 크기를 지배하면 안 된다.
FIGURE_HINT_MAX_CHARS = 2000
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
- Use only explicit primitive elements: svg, g, line, path, circle, ellipse, rect,
  polyline, polygon, text, tspan, title, desc. Do not use CSS, style blocks, class,
  transforms, script, foreignObject, image, use, href, external URLs, filters, masks,
  animation, or event handlers. The output is sanitized and anything outside this
  deterministic subset is rejected.
- The root must have a finite positive viewBox exactly in the form "0 0 W H". Put every
  visible stroke and label fully inside it with comfortable padding.
- Put labels away from geometry. If a label must sit over a guide/measurement line, use
  paint-order="stroke" stroke="#fff" and an adequate white stroke halo so the glyph stays
  readable. Never let labels collide with each other.

STRUCTURED GEOMETRY (preferred for circle/point/segment/angle diagrams): after <desc>,
emit a <figure-spec>...</figure-spec> block containing strict JSON FigureSpec v2. The
renderer will compile this JSON itself and ignore your handwritten SVG geometry. Omit
the block for unsupported charts, curves, solids, or photos. Use this compact schema:
{"version":2,"theme":"exam-thin","points":{"O":[94,78],
"A":{"type":"on_circle","circle":"c","angle":130},
"P":{"type":"intersection","segments":["AC","BD"]}},
"circles":{"c":{"center":"O","radius":68}},
"segments":{"AC":["A","C"],"BD":["B","D"]},
"angles":{"DPC":{"vertex":"P","points":["D","C"],"label":"x°"}},
"dimensions":{"AC_len":{"points":["A","C"],"label":"12 cm",
"side":"auto","offset":16,"inset":3}},
"labels":{"A":"A","P":"P"}}
All referenced points must be defined, intersections must lie inside both finite
segments, names are globally unique, and unknown fields are rejected.
⚠️ Names live in ONE namespace: an angle or dimension key must NOT reuse a point name
("A") or a segment name ("AB"). Prefix them — angles ``angA``/``angDPC``, dimensions
``dimAB`` — or compilation fails with "duplicate geometry name". A curved dashed
length guide must use `dimensions`, never a hand-positioned path: side `auto` lets the
engine choose left/right and increase curvature until it clears lines and A/B/C labels.
Include `dimensions` only when the source visibly contains a length guide or value;
otherwise omit it rather than inventing a measurement.
Prefer omitting canvas so the engine auto-fits without clipping. XML-escape label text.

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
   b) for a supported simple geometry, the optional <figure-spec> JSON block described
      above; otherwise omit it.
   c) then the SVG element <svg ...> ... </svg> that reproduces exactly that <desc>.
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


def _vision_to_svg(image: Image.Image, hint: str, api_key: str | None,
                   feedback: str | None = None) -> dict:
    """크롭 이미지를 Claude 비전에 보여주고 SVG 재현을 요청.

    반환: {"vectorizable": bool, "confidence": float, "svg": str}
    호출/파싱 실패 시 vectorizable=False.
    """
    import anthropic

    out = {"vectorizable": False, "confidence": 0.0, "svg": "", "desc": ""}
    try:
        # 병렬 그림 재생성(_resolve_figures) 버스트의 429/5xx 를 SDK 백오프로 흡수.
        client = anthropic.Anthropic(api_key=api_key or get_api_key(), max_retries=2)
        b64 = image_to_base64(image, format="PNG")
        user_text = "이 크롭 그림을 위 규칙대로 재현하세요."
        if hint:
            user_text += ("\n참고 설명(부정확할 수 있음): "
                          + str(hint)[:FIGURE_HINT_MAX_CHARS])
        if feedback:
            # 자동 검수의 구체적 실패만 전달한다. 이전 SVG 전체를 다시 싣지 않아도 같은
            # 이미지가 메시지에 있으므로 모델은 진단을 반영해 새로 작도할 수 있다.
            user_text += ("\n\n이전 작도는 자동 품질 검사에서 탈락했습니다. 아래 항목을 "
                          "모두 고쳐 SVG를 처음부터 다시 만드세요:\n- "
                          + feedback[:1600].replace("\n", "\n- "))
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
    desc_match = re.search(r"<desc>(.*?)</desc>", text, re.S | re.I)
    if desc_match:
        out["desc"] = re.sub(r"\s+", " ", desc_match.group(1)).strip()
    # 3) 지원되는 단순 기하라면 모델 좌표 SVG 대신 엄격한 FigureSpec을 채택한다.
    # JSON 파싱 실패 자체는 후보 오류로 보존해 교정 프롬프트가 한 번 돌아가게 한다.
    spec_match = re.search(r"<figure-spec>\s*(.*?)\s*</figure-spec>", text, re.S | re.I)
    if spec_match:
        try:
            parsed_spec = json.loads(spec_match.group(1))
            out["figure_spec"] = parsed_spec
        except Exception as exc:  # noqa: BLE001
            out["figure_spec_error"] = f"FigureSpec JSON 파싱 실패: {exc}"
    return out


def _assess_generated_svg(svg: str):
    """모델 SVG를 보안 정제하고 구조+픽셀 품질 게이트에 통과시킨다.

    import를 지연해 `figure_quality -> figure_svg -> figure_generator._svg_to_png_bytes`
    의 렌더 시점 의존이 모듈 import 순환으로 번지지 않게 한다.
    """
    from core.figure_quality import assess_svg

    return assess_svg(svg, run_pixel_lint=True)


def _assessment_feedback(assessment) -> str:
    """재작도 모델에 줄 수 있는 짧고 결정적인 실패 진단."""
    rows = list(getattr(assessment, "security_issues", ()) or ())
    rows.extend(getattr(assessment, "issues", ()) or ())
    return "\n".join(dict.fromkeys(str(v) for v in rows if str(v).strip()))


def _compile_structured_candidate(result: dict) -> tuple[str | None, str | None]:
    """Compile optional FigureSpec; otherwise return the model's raw SVG.

    A present-but-invalid spec is never silently bypassed with the accompanying
    handwritten SVG.  That would discard the semantic validation exactly when
    the model opted into it.
    """

    if result.get("figure_spec_error"):
        return None, str(result["figure_spec_error"])
    if "desc" in result and not str(result.get("desc") or "").strip():
        return None, "그림 의미 전사(<desc>)가 비어 있음"
    if "figure_spec" not in result:
        return result.get("svg") or None, None
    try:
        from core.figure_scene import compile_figure_spec

        scene = compile_figure_spec(result["figure_spec"])
        inventory_issue = _semantic_inventory_issue(scene, result.get("desc", ""))
        if inventory_issue:
            return None, inventory_issue
        return scene.render_svg(), None
    except Exception as exc:  # noqa: BLE001 — invalid model data becomes feedback
        return None, f"FigureSpec 검증 실패: {type(exc).__name__}: {exc}"


def _semantic_inventory_issue(scene, desc: str) -> str | None:
    """Cross-check structured labels against the model's own transcription.

    This is not image understanding; it is a deterministic anti-omission gate.
    Every explicit point/angle/dimension label compiled into the scene must occur in the
    preceding transcription, and the transcription may not name an additional
    standalone Latin point that the spec silently dropped.
    """

    normalized = str(desc or "").strip()
    if not normalized:
        # Direct/internal FigureSpec calls need no transcription.  Model output
        # does: `_vision_to_svg` always sets ``desc`` (possibly empty), so only
        # enforce when the key is present at the caller below.
        return None
    expected = {label.text for label in scene.labels.values()}
    expected.update(angle.label for angle in scene.angles.values() if angle.label)
    expected.update(dimension.label for dimension in scene.dimensions.values()
                    if dimension.label)
    missing = sorted(label for label in expected if label not in normalized)
    if missing:
        return "FigureSpec 의미 목록 불일치: 전사에 없는 라벨 " + ", ".join(missing)
    transcript_points = set(re.findall(r"(?<![A-Za-z])([A-Z])(?![A-Za-z])", normalized))
    scene_points = {label.text for label in scene.labels.values()
                    if re.fullmatch(r"[A-Z]", label.text)}
    omitted = sorted(transcript_points - scene_points)
    if omitted:
        return "FigureSpec 의미 목록 불일치: spec에서 누락된 점 " + ", ".join(omitted)
    return None


def _safe_png_path(out_dir: str, basename: str) -> str:
    """Resolve a bounded leaf filename inside *out_dir* (no traversal/overwrite)."""

    if (not isinstance(basename, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", basename)):
        raise ValueError("basename은 영문/숫자/_/-로 된 안전한 파일명이어야 함")
    root = os.path.abspath(out_dir)
    path = os.path.abspath(os.path.join(root, f"{basename}.png"))
    if os.path.commonpath((root, path)) != root:
        raise ValueError("출력 파일이 out_dir 밖을 가리킴")
    return path


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
    png_path = _safe_png_path(out_dir, basename)
    image = _flatten_white(image)  # 알파→흰배경(검은선 보존), 이후 비전·크롭 공통

    # 사진 힌트면 비전 호출 없이 곧장 크롭(비용/지연 절약). 그 외엔 재생성 시도.
    photo_hint = hint.strip().lower().startswith("[photo]") if hint else False
    if not photo_hint:
        feedback = None
        for attempt in range(SVG_GENERATION_ATTEMPTS):
            res = _vision_to_svg(image, hint, api_key, feedback=feedback)
            if not (res["vectorizable"] and res["confidence"] >= CONFIDENCE_THRESHOLD
                    and (res.get("svg") or res.get("figure_spec")
                         or res.get("figure_spec_error"))):
                logger.info("재생성 미채택(vec=%s conf=%.2f) → 크롭 폴백: %s",
                            res["vectorizable"], res["confidence"], basename)
                break

            candidate_svg, compile_issue = _compile_structured_candidate(res)
            if compile_issue:
                feedback = compile_issue
                logger.warning("구조화 도형 탈락(%d/%d): %s — %s",
                               attempt + 1, SVG_GENERATION_ATTEMPTS, basename, feedback)
                if attempt + 1 < SVG_GENERATION_ATTEMPTS:
                    continue
                break

            try:
                assessment = _assess_generated_svg(candidate_svg)
            except Exception as e:  # noqa: BLE001 — 검수기 자체 실패도 fail-closed
                feedback = f"SVG 품질 검사 실패: {type(e).__name__}: {e}"
                logger.warning("SVG 품질 검사 예외: %s — %s", basename, feedback)
                break
            if not assessment.accepted:
                feedback = _assessment_feedback(assessment) or "SVG 품질 게이트를 통과하지 못함"
                logger.warning("SVG 품질 게이트 탈락(%d/%d): %s — %s",
                               attempt + 1, SVG_GENERATION_ATTEMPTS, basename,
                               feedback.replace("\n", "; ")[:500])
                infrastructure_failure = any(
                    str(issue).startswith("pixel lint failed:")
                    for issue in (getattr(assessment, "issues", ()) or ())
                )
                if attempt + 1 < SVG_GENERATION_ATTEMPTS and not infrastructure_failure:
                    continue
                break

            # 렌더에는 반드시 sanitize가 끝난 SVG만 쓴다. 모델 원문을 다시 쓰면 보안
            # 정제와 allowlist가 무력화된다.
            png = _svg_to_png_bytes(assessment.sanitized_svg)
            if not png:
                logger.info("SVG 렌더 실패(%d/%d): %s", attempt + 1,
                            SVG_GENERATION_ATTEMPTS, basename)
                break
            try:
                # resvg 출력은 투명 배경 → 흰 배경으로 평탄화(소비처에서 검정화 방지)
                import io as _io
                _im = _flatten_white(Image.open(_io.BytesIO(png)))
                _buf = _io.BytesIO(); _im.save(_buf, format="PNG"); png = _buf.getvalue()
                with open(png_path, "wb") as f:
                    f.write(png)
                logger.info("그림 재생성 성공(conf=%.2f, attempt=%d): %s",
                            res["confidence"], attempt + 1, basename)
                return png_path, "svg"
            except Exception as e:  # noqa: BLE001
                logger.warning("재생성 PNG 저장 실패 — 크롭 폴백: %s", e)
                break

    # 폴백: 원본 크롭 raster
    p = _save_raster(image, png_path)
    if p:
        return p, "crop"
    return None, "none"
