"""문제 경계(크롭) 검출 — Gemini 3.5 Flash 우선, Claude 폴백.

페이지 이미지에서 각 문제(및 그림/표) 영역의 바운딩 박스를 검출한다.
좌표는 0~1로 정규화(좌상단 원점, x=가로비율, y=세로비율)되어 이미지 크기와 무관.
사용자는 GUI에서 이 박스를 드래그로 조정한 뒤, 박스별로 개별 OCR 한다.

bbox 그라운딩은 Gemini 가 더 정확하다(mathg-gen 도 Gemini 3 Flash 사용). 따라서
Gemini 키가 있으면 Gemini 로 검출하고, 없으면 Claude 로 폴백한다. 두 모델 모두
``[yMin, xMin, yMax, xMax]`` 0~1000 포맷으로 출력하도록 동일 프롬프트를 쓴다.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field

from PIL import Image
import anthropic

from core.pdf_handler import image_to_base64
from utils.config import get_api_key, get_gemini_key, CLAUDE_MODEL, GEMINI_MODEL

logger = logging.getLogger(__name__)


# 컬럼별 여백 보강(0~1 정규화). 좌측은 문항번호 잘림 방지로 크게, 우측은 소폭.
_LEFT_PAD = 0.025
_RIGHT_PAD = 0.015
_COLUMN_GAP_MIN = 0.20   # 정렬된 x0 간격이 이 이상이면 2단 경계로 인정


@dataclass
class CropBox:
    """정규화 바운딩 박스(0~1) + 메타."""
    x0: float
    y0: float
    x1: float
    y1: float
    kind: str = "problem"          # problem | figure | table | artwork
    number: int | None = None      # 문제 번호(있으면)
    qtype: str = ""                # choice | essay (디버그/후처리)
    note: str = ""                 # 하단 경계 근거(디버그)

    def clamp(self) -> "CropBox":
        """좌표를 [0,1]로 클램프하고 정렬(x0<x1, y0<y1)."""
        x0, x1 = sorted((max(0.0, min(1.0, self.x0)), max(0.0, min(1.0, self.x1))))
        y0, y1 = sorted((max(0.0, min(1.0, self.y0)), max(0.0, min(1.0, self.y1))))
        return CropBox(x0, y0, x1, y1, self.kind, self.number)

    def to_pixels(self, w: int, h: int) -> tuple[int, int, int, int]:
        """정규화 좌표 → 픽셀 (left, top, right, bottom)."""
        return (int(self.x0 * w), int(self.y0 * h),
                int(self.x1 * w), int(self.y1 * h))

    def crop_image(self, image: Image.Image, pad: float = 0.0) -> Image.Image:
        """이미지에서 이 박스 영역을 잘라 반환(pad: 정규화 여백)."""
        w, h = image.size
        b = CropBox(self.x0 - pad, self.y0 - pad,
                    self.x1 + pad, self.y1 + pad, self.kind, self.number).clamp()
        left, top, right, bottom = b.to_pixels(w, h)
        if right <= left or bottom <= top:
            return image
        return image.crop((left, top, right, bottom))


_CROP_PROMPT = """You are analyzing ONE page of a Korean math exam. For EVERY problem on the page, output a crop box that tightly encloses the whole problem.

Coordinate system: [yMin, xMin, yMax, xMax] on a 0-1000 grid over the FULL PAGE. yMin = top edge, xMin = left edge, 1000 = bottom / right edge.

Page layout: Korean exam pages are usually TWO COLUMNS. Read the LEFT column top-to-bottom first, then the RIGHT column. A problem stays entirely within ONE column — never let a crop box span both columns.

🚨 **CRITICAL — DISTINGUISH PRINTED PROBLEM CONTENT FROM STUDENT HANDWRITING (글자체·획 특성 기반)**

Korean exam papers are often photographed AFTER a student has written on them. The PRINTED text and the HANDWRITTEN ink have **dramatically different visual character** — use these traits to tell them apart:

**PRINTED content** (problem text, figures, numbers) — the ONLY thing that belongs in the crop box:
  - **Stroke uniformity**: every glyph has *consistent, even-thickness* strokes (typeset font output — width within 10% along a stroke).
  - **Color**: pure black ink, no red/blue/green pigment.
  - **Geometry**: characters sit on a strict baseline grid; letterforms are *geometric and repeatable* (every "ㅇ" looks identical, every "5" looks identical).
  - **Alignment**: text wraps in straight columns; figures have crisp clean line art.

**STUDENT HANDWRITING** (solutions, scribbles, circled answers) — MUST be EXCLUDED from every crop box:
  - **Stroke variability**: 굵기가 *들쭉날쭉* — same pen produces 1px and 3px within the same stroke (pen pressure variation). Stroke ends often taper or blob.
  - **Color**: typically red marker (사용자 정답·답안 동그라미), blue ballpoint (풀이식), or *uneven* black (compared to print's pure black).
  - **Irregular character shape**: every "x" looks slightly different, every digit "5" has its own quirks; characters often slanted, not on a baseline; size variation within one expression.
  - **Free-form curves**: circled numbers (사용자가 정답 표시), arrows pointing into the problem, factor trees with diagonal lines, freehand "=" lines or check marks.
  - **Location**: typically in the *blank space below the (N점) marker* or *between problems*, where the student answered.

Common student handwriting to IGNORE:
  - Red/blue pen scribbles in the answer space below the problem
  - Circled numbers (사용자 정답 표시) drawn over or beside the problem
  - Freehand calculations, factoring trees, arrows pointing at the problem
  - Numbers written in the blank space between problems (e.g. "64", "36 3", "9 81" written between two printed problems)
  - 빨간 마커로 그린 동그라미 (학생이 자신의 풀이 답을 표시) — 절대 박스 안에 포함 X

The space where the student wrote is BELOW the printed problem's last text/figure line. The crop MUST end at that last printed line — NOT extend into the handwriting zone. **빨간/파란 잉크가 박스 후보 안에 보이면 즉시 박스 bottom 을 그 위 인쇄 줄까지 끌어올리세요.**

---

🎨 **4-CLASS CROP CLASSIFICATION (class field)**:

거의 모든 박스는 class="problem" (한 문항 전체 — 텍스트 + 모든 내부 시각 요소 포함). 다음은 *드문* 예외:
  - **"figure"**: 페이지에 *문제와 분리된 standalone 기하 도형*. 일반적인 *문항 안의 도형* 은 problem 박스에 *포함* — 별도 figure 박스 X.
  - **"table"**: 페이지에 *문제와 분리된 standalone 표* (시간표/달력/점수표). 문항 안의 표는 problem 박스 안.
  - **"artwork"**: 페이지에 *문제와 분리된 standalone 회화/사진/실사 이미지* (vectorize 불가). 문항 안에서 작품 referencing 하면 problem 박스 안에 포함.
  - **"problem"** (default, 99% case): 한 문항 전체. 안에 어떤 시각 요소가 있어도 problem 박스 안에 모두 포함.

🚨 결정 룰 (의심 시 "problem"): 박스가 문항 번호 ([서술형 N], 1., 2. 등) 를 포함하면 → "problem".

---

For each problem, decide its TYPE and find its crop box:

1. CHOICE problem (객관식 — has multiple-choice options ① ② ③ ④ ⑤):
   - Crop TOP = the line of the printed problem number.
   - Crop BOTTOM = the bottom of the LAST option row (the row holding the highest marker — usually ⑤, or ④ if only 4 options). Options may be one-per-line OR in a 2/3-column grid; the last marker is always in the last option row.
   - Any figure sits between the problem text and the options, so this box always contains it.
   - type = "choice", endMarkerKind = "choice".

2. SIMPLE ESSAY problem (서술형 — NO ①②③④⑤ options, NO sub-numbers like (1)(2); a single points marker like "(7점)" or "(8점)"):
   - Crop TOP = the line of the printed problem number ([서술형 N] or N. or similar).
   - Crop BOTTOM = the line containing the "(N점)" points marker.
   - 🚨 **HARD STOP at the (N점) line.** The space below it is where the student writes their solution — it is NOT part of the printed problem. Do NOT extend into that blank/handwritten zone.
   - 🚨 **IGNORE all student handwriting** in the answer space below: scribbled numbers, factor trees, circled answers, red pen marks.
   - EXCEPTION — printed figure (clean line art, uniform stroke, NOT handwriting): if a printed figure sits below the (N점) marker as part of the problem, extend the bottom to include the figure.
   - type = "essay", endMarkerKind = "points".

3. SPLIT ESSAY problem (서술형 with sub-numbered parts (1), (2), …):
   The WHOLE thing (problem header + all printed sub-parts) is ONE problem → ONE crop box.
   - Crop TOP = the line of the printed problem number.
   - Crop BOTTOM = the bottom of the LAST printed sub-part's text line (e.g., the line containing "(2) 완전제곱식을 이용하여 구하시오.").
   - 🚨 Sub-parts (1)(2)(3) are separated by BLANK SPACE for the student to solve. That blank space — and any handwriting in it — is INSIDE the single box (you cannot split sub-parts), BUT the box must STILL end at the last printed sub-part's text line, NOT at the bottom of the student's handwriting after the last sub-part.
   - 🚨 Recognize sub-part markers "(1)" "(2)" "(3)" (with parenthesis). Distinguish from option markers "①②③" and from inline "(N점)".
   - EXCEPTION — printed figure below the last sub-part text: include the figure.
   - type = "essay", endMarkerKind = "total".

🚨 **사용자 보고 사례 (반드시 따를 것)**:
  사례 A — 서술형 (8점), 풀이 영역 침범 (잘못): 빈 풀이 공간에 빨간 펜으로 "9 3 48" 학생 필기. 잘못된 크롭: 박스가 "(8점)" 줄을 넘어 "48" 까지 포함. 올바른 크롭: 박스 bottom = "(8점)" 줄. 그 아래 학생 필기는 박스 *밖*.
  사례 B — 서술형 (1)(2) 서브문항: 올바른 크롭 top = "[서술형 N]" 줄, bottom = "(2) …구하시오." 줄. (1)(2) 사이 학생 필기는 박스 안에 들어가지만, bottom edge 는 (2) 의 인쇄 텍스트 줄에서 정확히 끝남.

Rules:
- Bias toward OVER-cropping *horizontally* (LEFT edge must include the printed number; RIGHT edge must include the rightmost content). Pad ~15 units on left/right.
- Bias toward UNDER-cropping *vertically* on the bottom for essay problems — never extend past the last printed problem element (last sub-part text, last (N점), last printed figure) into the student's answer space.
- 🚨 **ADJACENT BOXES MUST NOT OVERLAP VERTICALLY (within a column).** Each printed problem occupies a *disjoint* vertical band. Box N's BOTTOM (yMax) must sit ABOVE box N+1's TOP (yMin) — leave a small gap at the blank line between problems; never let consecutive boxes share a y-range. A box's TOP = its own problem-number line, its BOTTOM = its own last printed element — so a box must NEVER reach down into the next problem's number line, nor up into the previous problem's last line. If two problems are tightly stacked, place the boundary at the blank gap between them (prev problem's last printed line = prev yMax; next problem's number line = next yMin), with prev.yMax < next.yMin. (대륜중 중1 #2~4: 인접 박스가 ~1% 겹쳐 옆 문항 자투리가 크롭에 섞였음, 2026-06-11.)
- Only emit boxes for actual printed problems — never for empty answer space, the page header, or page furniture.
- 문항번호를 읽을 수 있으면 number 에 기록.

## OUTPUT — pure JSON only:
```json
{
  "items": [
    {"number": 8, "type": "choice", "class": "problem", "cropBox": [100, 50, 280, 480], "endMarkerKind": "choice", "note": "⑤ bottom-right"}
  ]
}
```
- cropBox = [yMin, xMin, yMax, xMax] on the 0-1000 grid.
- type = "choice"|"essay", class = "problem"|"figure"|"table"|"artwork", endMarkerKind = "choice"|"points"|"total".
- note: short reason for the bottom edge (e.g., "⑤ bottom-right", "(8점) line", "last sub-part (2)").
- List in reading order: left column top→bottom, then right column.
"""


def _fallback_reason(err: Exception) -> str:
    """Gemini 실패 예외 → 사용자가 알아볼 한 줄 원인(크레딧/레이트리밋/키/기타)."""
    low = str(err).lower()
    if any(k in low for k in ("credit", "depleted", "billing", "prepay", "balance")):
        return "Gemini 크레딧 소진(결제 필요) — AI Studio 에서 충전"
    if any(k in low for k in ("api key", "api_key", "permission", "unauthor",
                              "invalid", "401", "403")):
        return "Gemini 키/권한 오류 — config.json 의 GEMINI_API 확인"
    if any(k in low for k in ("429", "rate", "quota", "resource", "exhaust",
                              "503", "500", "unavailable", "overload", "timeout", "deadline")):
        return "Gemini 레이트리밋/일시 오류 — 잠시 후 재시도"
    return f"Gemini 오류: {str(err)[:120]}"


def _is_permanent(err: Exception) -> bool:
    """재시도해도 소용없는 영구 오류(크레딧 소진·키/권한 오류)면 True."""
    low = str(err).lower()
    return any(k in low for k in ("credit", "depleted", "billing", "prepay", "balance",
                                  "api key", "api_key", "permission", "unauthor",
                                  "invalid", "401", "403"))


def detect_crops(image: Image.Image, api_key: str | None = None,
                 on_fallback=None) -> list[CropBox]:
    """페이지 이미지에서 문제 경계 박스 리스트를 검출.

    Gemini 키가 있으면 Gemini 3.5 Flash(bbox 정확)로, 없으면 Claude 로 검출한다.
    Gemini 가 실패해 **Claude 로 폴백**하면 그 사실·원인을 로그(``시험지한글화.log``)에
    남기고 ``on_fallback(reason)`` 콜백(있으면)으로 호출자(GUI)에 알린다 — 조용한 폴백으로
    "크롭이 갑자기 이상해졌다"의 원인을 못 찾던 문제 방지(사용자 2026-06-09).
    """
    gem_key = get_gemini_key()
    gem_err: Exception | None = None
    if gem_key:
        # 일시적 실패(레이트리밋 429·5xx·타임아웃)는 재시도로 구제 — 연속 변환 시 Gemini
        # 레이트리밋 버스트로 전 페이지가 0개 검출되던 문제(2026-06-05). 영구 오류(크레딧
        # 소진·키/권한)는 재시도해도 무의미하므로 즉시 폴백.
        for attempt in range(3):
            try:
                return _detect_with_gemini(image, gem_key)
            except Exception as e:  # noqa: BLE001
                gem_err = e
                permanent = _is_permanent(e)
                logger.warning("Gemini 크롭 검출 실패(%d/3, 영구=%s): %s",
                               attempt + 1, permanent, e)
                if permanent or attempt == 2:
                    break
                time.sleep(1.5 * (attempt + 1))
    # ⭐ Claude 폴백 폐지(2026-08-07, 사용자: "claude 는 이제 변환기에서 제외").
    # 변환기는 Gemini(인식) + DeepSeek(정답·해설)만 쓴다. 실패 원인을 그대로 올려
    # 워커가 한도 초과/키 무효를 판정해 즉시 중단할 수 있게 한다.
    if gem_err is not None:
        raise RuntimeError(f"Gemini 크롭 검출 실패: {gem_err}") from gem_err
    raise RuntimeError(
        "GEMINI_API_KEY 가 설정되지 않았습니다 — config.json 에 키를 넣어 주세요.")


def _detect_with_claude(image: Image.Image, api_key: str | None = None) -> list[CropBox]:
    """Claude Vision 으로 크롭 검출(폴백)."""
    # 병렬 검출 버스트의 429/5xx 를 SDK 백오프로 흡수(max_retries 2→5).
    client = anthropic.Anthropic(api_key=api_key or get_api_key(), max_retries=5)
    b64 = image_to_base64(image, format="PNG")
    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=8192,
        # 좌표 검출은 결정적 작업 — 기본 1.0이면 bbox 가 매 호출 흔들린다.
        temperature=0.0,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64",
                                              "media_type": "image/png", "data": b64}},
                {"type": "text", "text": _CROP_PROMPT},
            ],
        }],
    )
    return _parse_crops(msg.content[0].text)


def _detect_with_gemini(image: Image.Image, api_key: str) -> list[CropBox]:
    """Gemini 3.5 Flash 로 크롭 검출(mathg-gen 과 동일 모델·설정).

    bbox 그라운딩이 Claude 보다 정확하다. 출력은 동일하게 items[].cropBox
    ``[yMin, xMin, yMax, xMax]`` 0~1000 → ``_parse_crops`` 로 처리.
    """
    from google import genai
    from google.genai import types

    import base64
    b64 = image_to_base64(image, format="PNG")
    img_bytes = base64.b64decode(b64)

    client = genai.Client(api_key=api_key)
    cfg_kwargs = dict(
        response_mime_type="application/json",
        temperature=0.1,
        max_output_tokens=65536,
    )
    # 사고(thinking) 끔 — 좌표 검출에 사고는 불필요한데 출력 단가로 과금된다
    # (ocr_engine._gemini_generate 의 동일 설정 주석 참조). flash 한정 + 구 SDK 방어.
    config = None
    if "flash" in (GEMINI_MODEL or "").lower():
        try:
            config = types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=0), **cfg_kwargs)
        except Exception:   # noqa: BLE001
            config = None
    if config is None:
        config = types.GenerateContentConfig(**cfg_kwargs)
    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            types.Part.from_bytes(data=img_bytes, mime_type="image/png"),
            _CROP_PROMPT,
        ],
        config=config,
    )
    return _parse_crops(resp.text or "")


def _parse_crops(text: str) -> list[CropBox]:
    """응답 텍스트에서 items JSON 파싱 → CropBox 리스트.

    mathg-gen 포맷: ``cropBox = [yMin, xMin, yMax, xMax]`` (0~1000 그리드).
    내부 표준(0~1, [x0,y0,x1,y1])으로 변환한다.
    """
    t = text.strip()
    if "```json" in t:
        t = t.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in t:
        t = t.split("```", 1)[1].split("```", 1)[0].strip()
    if not t.startswith("{"):
        i = t.find("{")
        if i >= 0:
            t = t[i:]
        j = t.rfind("}")
        if j >= 0:
            t = t[:j + 1]
    try:
        data = json.loads(t)
    except json.JSONDecodeError as e:
        # ⚠️ **예외로 올린다** — 빈 리스트 반환은 "문항 없음"(정상 빈 페이지)과 구별 불가라
        # 잘린/깨진 응답이 재시도·폴백 없이 페이지 통째 소실로 둔갑하던 결함(적대리뷰 A-3).
        # 호출부(_detect_with_gemini/_claude)가 detect_crops 의 재시도 루프·폴백·사용자 노출로
        # 받아낸다. (진짜 빈 페이지는 valid JSON + 빈 items 라 이 경로를 안 탄다.)
        logger.warning("크롭 JSON 파싱 실패(재시도/폴백 유도): %s", e)
        raise ValueError(f"크롭 JSON 파싱 실패: {e}") from e

    # 신규 "items"(cropBox) 우선, 구버전 "crops"(bbox) 하위호환.
    raw_items = data.get("items")
    legacy = raw_items is None
    if legacy:
        raw_items = data.get("crops", [])

    boxes: list[CropBox] = []
    for c in raw_items:
        bb = c.get("bbox") if legacy else c.get("cropBox")
        if not (isinstance(bb, list) and len(bb) == 4):
            continue
        try:
            v = [float(x) for x in bb]
        except (TypeError, ValueError):
            continue
        if legacy:
            # 구포맷: [x0, y0, x1, y1] 0~1
            x0, y0, x1, y1 = v
        else:
            # mathg-gen: [yMin, xMin, yMax, xMax] 0~1000 → [x0,y0,x1,y1] 0~1
            y_min, x_min, y_max, x_max = v
            x0, y0, x1, y1 = x_min / 1000.0, y_min / 1000.0, x_max / 1000.0, y_max / 1000.0
        box = CropBox(x0, y0, x1, y1,
                      kind=c.get("class", c.get("kind", "problem")),
                      number=c.get("number"),
                      qtype=c.get("type", ""),
                      note=c.get("note", "")).clamp()
        # 면적이 너무 작은 박스는 노이즈로 제외
        if (box.x1 - box.x0) > 0.02 and (box.y1 - box.y0) > 0.02:
            boxes.append(box)
    return _pad_columns(boxes)


def _estimate_column_split(boxes: list[CropBox]) -> float | None:
    """박스들의 x0 분포에서 2단 분할선을 동적 추정(없으면 None=단일 컬럼).

    한 컬럼 문항들은 같은 좌측 여백에 정렬돼 x0가 좁게 뭉친다. 2단이면 x0가 두
    무리로 갈리고 큰 간격이 생긴다 — 정렬된 x0 최대 간격이 임계 이상이면 그
    중점을 분할선으로 본다.
    """
    xs = sorted(b.x0 for b in boxes)
    if len(xs) < 2:
        return None
    max_gap, split = 0.0, 0.0
    for i in range(1, len(xs)):
        gap = xs[i] - xs[i - 1]
        if gap > max_gap:
            max_gap, split = gap, (xs[i] + xs[i - 1]) / 2
    return split if max_gap >= _COLUMN_GAP_MIN else None


def _pad_columns(boxes: list[CropBox]) -> list[CropBox]:
    """컬럼 인식 여백 보강: 좌단(또는 단일컬럼) 박스는 좌측을 더 확장."""
    split = _estimate_column_split(boxes)
    out: list[CropBox] = []
    for b in boxes:
        is_left = split is None or b.x0 < split
        x0 = b.x0 - _LEFT_PAD if is_left else b.x0
        b2 = CropBox(x0, b.y0, b.x1 + _RIGHT_PAD, b.y1,
                     b.kind, b.number, b.qtype, b.note).clamp()
        out.append(b2)
    return out
