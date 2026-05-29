"""Claude Vision 기반 문제 경계(크롭) 검출.

페이지 이미지에서 각 문제(및 그림/표) 영역의 바운딩 박스를 검출한다.
좌표는 0~1로 정규화(좌상단 원점, x=가로비율, y=세로비율)되어 이미지 크기와 무관.
사용자는 GUI에서 이 박스를 드래그로 조정한 뒤, 박스별로 개별 OCR 한다.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from PIL import Image
import anthropic

from core.pdf_handler import image_to_base64
from utils.config import get_api_key, CLAUDE_MODEL

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


_CROP_PROMPT = """당신은 한국 수학 시험지 한 페이지의 레이아웃을 분석해, **각 문항의 크롭 박스**를 찾는 전문가입니다.

좌표계: bbox = [x0, y0, x1, y1], **0~1 정규화** (좌상단 (0,0), 우하단 (1,1), x=가로비율 y=세로비율, x0<x1, y0<y1).

페이지 구성: 한국 시험지는 보통 **2단(좌우 컬럼)** 입니다. **좌측 컬럼을 위→아래로 먼저, 그다음 우측 컬럼**. 한 문항은 한 컬럼 안에만 — 박스가 두 컬럼을 가로지르면 안 됩니다.

## 🚨 가장 중요 — 인쇄물 vs 학생 손글씨 구분
시험지는 학생이 풀이를 적은 뒤 촬영된 경우가 많습니다. **인쇄된 문항 내용만** 박스에 넣고 **학생 손글씨는 반드시 제외**하세요.
- **인쇄물**(박스에 포함): 균일한 굵기의 활자, 순수 검정, 일정한 베이스라인, 깨끗한 도형 선.
- **학생 손글씨**(박스에서 제외): 굵기가 들쭉날쭉(1px↔3px), **빨강/파랑 펜**, 불규칙·기울어진 글씨, 자유곡선. 정답에 친 **동그라미**, 풀이식, 화살표, 인수분해 나무, 문항 사이 빈칸에 적은 숫자.
- 학생 필기는 보통 `(N점)` 마커 아래 빈 풀이 공간이나 문항 사이에 있습니다. **빨강/파랑 잉크가 보이면 즉시 박스 하단을 그 위로 끌어올리세요.** 크롭은 마지막 **인쇄된** 줄에서 끝나야 합니다.

## 문항별 끝 경계 규칙
1. **객관식**(보기 ①②③④⑤ 있음): 위=문항번호 줄, 아래=**마지막 보기 줄 하단**(보통 ⑤, 4지선다면 ④). 보기가 다단이어도 마지막 보기가 든 줄까지. 딸린 그림은 본문과 보기 사이에 있어 자동 포함됨. → type="choice".
2. **단순 서술형**(보기 없음, `(N점)`/`[N점]` 배점 하나): 위=문항번호, 아래=**배점 `(N점)` 줄에서 HARD STOP**. 그 아래 학생 풀이 공간은 제외. 단, 배점 아래에 **인쇄된 도형**이 문항 일부면 도형까지 포함. → type="essay".
3. **분할 서술형**(소문항 (1)(2)… 있음): 헤더+모든 인쇄 소문항이 **하나의 박스**. 아래=**마지막 인쇄 소문항 텍스트 줄**(예 "(2) …구하시오."). 소문항 사이 빈칸·학생필기는 박스 안에 있을 수밖에 없지만, 하단은 마지막 소문항 인쇄 줄에서 끝. → type="essay".

## 분류 (class)
거의 모든 박스는 **"problem"**(문항 전체 — 텍스트+내부 도형·표·그림 모두 포함). 문항 *안의* 도형/표/그림은 별도로 빼지 말고 problem 박스에 포함하세요. 다음은 *드문* 예외(문항과 분리된 standalone 요소일 때만):
- **"figure"**: 문항과 분리된 독립 기하 도형(작도 가능한 line art).
- **"table"**: 문항과 분리된 독립 표(시간표·점수표 등).
- **"artwork"**: 문항과 분리된 독립 실사 이미지(회화·사진 — 벡터화 불가).
의심되면 **"problem"**. 박스가 문항번호를 포함하면 무조건 "problem".

## 기타
- 페이지 머리글(학교명·과목)·바닥글·페이지번호는 박스에 넣지 마세요.
- 문항번호를 읽을 수 있으면 number에 기록(못 읽으면 null).
- 좌우는 넉넉히(문항번호·우측 내용 안 잘리게), 서술형 하단은 인색하게(학생 답안 공간 침범 금지).

## 출력 (순수 JSON만)
```json
{
  "crops": [
    {"number": 8, "type": "choice", "kind": "problem", "bbox": [0.05, 0.10, 0.48, 0.28], "note": "⑤ 하단"}
  ]
}
```
- bbox=[x0,y0,x1,y1] 정규화, kind="problem"|"figure"|"table"|"artwork", type="choice"|"essay".
- note: 하단 경계를 정한 근거(디버그용, 예 "⑤ 하단", "(8점) 줄", "마지막 소문항 (2)").
- 위→아래, 좌단 전체→우단 순서로 나열.
"""


def detect_crops(image: Image.Image, api_key: str | None = None) -> list[CropBox]:
    """페이지 이미지에서 문제 경계 박스 리스트를 검출."""
    client = anthropic.Anthropic(api_key=api_key or get_api_key())
    b64 = image_to_base64(image, format="PNG")
    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2048,
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


def _parse_crops(text: str) -> list[CropBox]:
    """응답 텍스트에서 crops JSON 파싱 → CropBox 리스트."""
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
        logger.warning("크롭 JSON 파싱 실패: %s", e)
        return []

    boxes: list[CropBox] = []
    for c in data.get("crops", []):
        bbox = c.get("bbox")
        if not (isinstance(bbox, list) and len(bbox) == 4):
            continue
        try:
            x0, y0, x1, y1 = (float(v) for v in bbox)
        except (TypeError, ValueError):
            continue
        box = CropBox(x0, y0, x1, y1,
                      kind=c.get("kind", "problem"),
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
