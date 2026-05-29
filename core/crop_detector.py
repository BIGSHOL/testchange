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


@dataclass
class CropBox:
    """정규화 바운딩 박스(0~1) + 메타."""
    x0: float
    y0: float
    x1: float
    y1: float
    kind: str = "problem"          # problem | figure | table
    number: int | None = None      # 문제 번호(있으면)

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


_CROP_PROMPT = """당신은 한국 수학 시험지의 레이아웃을 분석하는 전문가입니다.
이 페이지 이미지에서 **각 문제(및 독립된 그림·표)의 경계 사각형**을 찾으세요.

## 규칙
1. 문제 하나당 박스 하나. 문제 번호, 본문, 선택지(①~⑤), 딸린 그림/표까지 **한 문제에 속한 것은 모두 포함**해 하나의 박스로 묶으세요.
2. 2단(좌우 2컬럼) 구성이면 좌측 문제들과 우측 문제들을 각각 별도 박스로. 컬럼을 가로지르지 마세요.
3. 좌표는 **0~1로 정규화**: 좌상단이 (0,0), 우하단이 (1,1). x=가로 비율, y=세로 비율.
4. 박스는 문제 내용을 꽉 채우되 옆 문제를 침범하지 마세요. 약간의 여백은 허용.
5. 페이지 상단 머리글(학교명·과목)·바닥글·페이지번호는 박스에 넣지 마세요.
6. 문제 번호를 읽을 수 있으면 number에 기록(못 읽으면 null).
7. 위에서 아래로, 좌에서 우로(2단이면 좌측 전체 후 우측) 순서대로 나열.

## 출력 (순수 JSON만)
```json
{
  "crops": [
    {"number": 8, "kind": "problem", "bbox": [0.05, 0.10, 0.48, 0.28]}
  ]
}
```
- bbox = [x0, y0, x1, y1] (정규화, x0<x1, y0<y1)
- kind = "problem" | "figure" | "table"
- 그림/표가 문제와 분리된 독립 요소면 kind를 figure/table로, 아니면 문제 박스에 포함.
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
                      number=c.get("number")).clamp()
        # 면적이 너무 작은 박스는 노이즈로 제외
        if (box.x1 - box.x0) > 0.02 and (box.y1 - box.y0) > 0.02:
            boxes.append(box)
    return boxes
