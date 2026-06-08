"""Claude Vision API를 이용한 수학 시험지 OCR 엔진."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from PIL import Image
import anthropic

logger = logging.getLogger(__name__)

from core.pdf_handler import image_to_base64
from utils.config import get_api_key, CLAUDE_MODEL, CLAUDE_MAX_TOKENS

# OCR 응답 토큰 예산: 수식이 많은 문항은 JSON 이 길어 8192 면 **잘려서**(max_tokens)
# JSON 이 깨지고 그 문항이 통째로 건너뛰어진다(실데이터 다사중 p2 박스2). 크롭 1개라도
# 넉넉히 준다. config 가 더 크면 그 값을 쓴다. (Claude Sonnet 4.x 출력 한계 내.)
OCR_MAX_TOKENS = max(int(CLAUDE_MAX_TOKENS), 16384)


@dataclass
class OCRQuality:
    """OCR 응답 검증 결과."""

    valid: bool = True
    warnings: list[str] = field(default_factory=list)
    question_count: int = 0
    equation_count: int = 0

# 한국어 수학 시험지 전용 OCR 프롬프트
EXAM_OCR_PROMPT = """당신은 한국 수학 시험지를 정밀하게 OCR하는 전문가입니다.
이미지에서 모든 텍스트와 수식을 정확하게 추출하세요.

## ⛔ 인쇄 텍스트만 읽기 — 손글씨/필기 절대 배제 (최우선 규칙!)
시험지는 **출제자가 인쇄한 활자(고정 폰트)** 로만 이루어져 있습니다. 학생이 연필·볼펜으로
쓴 **손글씨(풀이·낙서·동그라미·밑줄·체크·메모·정답 표시)는 문제의 일부가 아니므로 절대로
읽거나 출력하지 마세요.** 인쇄 활자가 아닌 모든 흔적은 무시합니다.
- 인쇄 활자 = 매끈하고 균일한 자모, 일정한 굵기·기울기, 정렬된 줄. → **읽는다.**
- 손글씨 = 삐뚤빼뚤·불균일한 획, 흘림체, 인쇄 글자 위에 겹쳐 쓴 흔적, 여백의 계산/낙서,
  보기·숫자에 그은 동그라미/사선/밑줄/체크. → **완전히 무시(출력 금지).**
- ⚠️ 손글씨를 수식으로 오인해 ``__xy__`` 같은 **비정상·의미불명 토큰을 만들지 마세요.**
  읽어서 인쇄 활자로 말이 안 되면(깨진 변수 나열, 맥락 없는 기호 덩어리) 그건 손글씨이거나
  오인식이므로 **버립니다.** 확신이 없으면 출력하지 않는 쪽을 택하세요.
- 손글씨를 지웠다고 해서 인쇄된 빈칸(□)·괄호·밑줄 서식까지 지우면 안 됩니다(그건 인쇄 활자).

## 핵심 원칙 (가장 중요!)
1. 이미지의 텍스트를 **한 글자씩 정확하게** 읽으세요. 추측·의역·요약 금지.
2. 원본 문장을 그대로 복사하듯이 적으세요. 단어를 바꾸거나 빼지 마세요.
3. 수식도 이미지에 보이는 그대로 추출. 숫자·계수·지수를 절대 바꾸지 마세요.
4. 한글 음절을 하나라도 빠뜨리거나 바꾸면 안 됩니다:
   - "거듭제곱" ≠ "기하적금" (X)  /  "옳은" ≠ "올은" (X)
   - "거실" ≠ "가설" (X)  /  "회전축" ≠ "위중" (X)
   - "알맞은" ≠ "오는" (X)  /  "민성이는" ≠ "기여는" (X)
5. **인쇄 활자가 아닌 손글씨/필기는 무시**(위 ⛔ 최우선 규칙). 손글씨를 문제 텍스트·수식으로
   출력하지 마세요.

## 문제 번호 규칙 (매우 중요!)
- 문제의 **주 번호**(1., 2., ... 20., 21.)를 반드시 number에 기록하세요.
- "19. [서술형 3]"이면 number는 **19**입니다 (3이 아닙니다!).
- "20. [서술형 4]"이면 number는 **20**입니다 (4가 아닙니다!).
- [서술형 N] 레이블은 contents의 텍스트에 포함하세요:
  {"type":"text","value":"[서술형 3] 아래 그림은..."}
- 페이지 상단의 학교명·과목명은 header에만 넣고, questions에 넣지 마세요.

## 출력 규칙
1. **JSON 형식으로만** 응답. 순수 JSON만 출력하세요.
2. 수식은 **LaTeX 형식**으로 변환. 인라인 수식은 type="equation", 독립행은 type="equation_block".
3. 선택지 번호는 ①②③④⑤를 1,2,3,4,5로 변환.
4. 배점은 **score 필드에 숫자만** (예: 3, 4, 5, 8). **본문 contents 텍스트에는 [N점]을 절대 넣지 마세요** (중복 출력 원인). 단, "[총 9점]"처럼 소문항 합계 총점은 본문에 그대로 두세요.

## 출력 JSON 구조
```json
{
  "header": "페이지 상단 텍스트 (과목명, 학년 등)",
  "questions": [
    {
      "number": 1,
      "score": 3,
      "contents": [
        {"type": "text", "value": "다음 식의 값을 구하시오."},
        {"type": "equation_block", "value": "\\\\frac{1}{2} + \\\\frac{1}{3}"},
        {"type": "figure", "value": "수직선 -3~5, 2 닫힌점", "bbox": [0.1, 0.4, 0.9, 0.6]}
      ],
      "choices": [
        {"number": 1, "contents": [{"type": "equation", "value": "\\\\frac{5}{6}"}]}
      ],
      "sub_questions": []
    }
  ]
}
```

## 수식/텍스트 분리 규칙
- **equation**: 영문 변수, 숫자, 수학 기호(+, -, =, ×, ÷), 분수, 지수 등 순수 수학 표현
- **text**: 한글 텍스트, 한글 괄호 내용("(가)", "(나)"), 조사, 문장부호
- 수식+한글이 섞인 문장은 반드시 분리:
  올바른 예: {"type":"equation","value":"a > 0"}, {"type":"text","value":"이고 "}, {"type":"equation","value":"b"}, {"type":"text","value":"는 정수일 때"}
- **모든 숫자(정수, 소수)도 반드시 equation 타입으로 분리**:
  올바른 예: {"type":"equation","value":"30"}, {"type":"text","value":"개의 공을"}
  잘못된 예: {"type":"text","value":"30개의 공을"} — 숫자가 텍스트에 포함되면 안 됩니다!
- 쉼표로 구분된 독립 수식은 개별 블록으로:
  {"type":"equation","value":"A=2^6"}, {"type":"text","value":", "}, {"type":"equation","value":"B=3^6"}
- □(빈칸) → {"type":"equation","value":"\\\\square"}

## 괄호 종류 구분 (매우 중요!)
- 소괄호 ( ), 중괄호 \\{ \\}, 대괄호 [ ]를 정확히 구분하세요.
- 중첩 괄호 문제에서 괄호 종류가 다른 것은 의도적입니다:
  - 올바른 예: 6x - [3y + 2x - \\{3x + \\square - (5x - 7y)\\}] (O)
  - 잘못된 예: 6x - (3y + 2x - (3x + \\square - (5x - 7y))) (X) — 모두 ()로 바꾸면 안 됩니다!

## 변수·기호 정확도 (매우 중요!)
- **x와 z를 혼동하지 마세요.** 같은 수식에 x가 있으면, 다른 곳의 같은 글자도 x입니다.
- **÷(나눗셈)와 +(덧셈)을 혼동하지 마세요.** ÷는 가로줄 위아래에 점이 있습니다.
- ≠ (\neq), ≤ (\leq), ≥ (\geq), < (\lt), > (\gt)를 정확히 구분.
- 여러 변수(x, y, z)가 있는 수식에서 **변수를 누락하지 마세요**:
  - (x^a y^b z^c)^d에서 z^c를 빠뜨리면 안 됩니다!
- **기하 도형 이름(점·선·면)은 정자(로만체)로**: 점·꼭짓점·원점·교점의 대문자 이름,
  삼각형/사각형/직선/선분 이름은 반드시 `\\mathrm{}` 로 감싸세요(한국 교과서 표기 — 변수
  이탤릭과 구분). 예: 점 A → `\\mathrm{A}`, 원점 O → `\\mathrm{O}`, 삼각형 ABC →
  `\\triangle \\mathrm{ABC}`, 선분 AB → `\\overline{\\mathrm{AB}}`, 직선 ℓ → `\\mathrm{l}`.
  (단, 함수·미지수로 쓰인 소문자 x,y,a,b 등은 그대로 이탤릭.)

## 지수(위첨자) 정확도 (매우 중요!)
- 지수는 글자가 작아서 오인식이 빈번합니다. 확대해서 확인하세요.
- **한 자릿수와 두 자릿수를 혼동하면 안 됩니다**: 2^{48} ≠ 2^{6}, x^{15} ≠ x^{5}
- 같은 문제의 여러 선택지에서 지수가 모두 같으면 오인식일 가능성이 높습니다.
- 각 선택지의 수식이 서로 **달라야** 합니다. 동일하면 오인식입니다.

## 순환소수
- 순환마디(점)는 LaTeX \\dot{}으로: 0.\\dot{2}\\dot{4} (24 순환)
- 점은 **순환마디의 첫 숫자와 마지막 숫자 위에만** 찍습니다: 0.3\\dot{7}\\dot{5} (X) / 0.\\dot{3}7\\dot{5} (O, 375 순환)
- "순환소수"라는 단어가 나오면 소수에 반드시 순환마디 점이 있습니다.

## 조건/보기 박스 (줄 구분 매우 중요!)
- 박스 안에 여러 항목이 나열되면 **각 항목을 불릿(•)으로 구분**하여 하나의 text 블록에 담으세요:
  {"type":"text","value":"<조건> • a, b를 분수로 나타낼 것 • 기약분수로 나타낼 것 • 순환마디에 점을 찍을 것"}
- 박스 제목은 "<조건>" 또는 "<보기>"로 표기하고, 항목 사이는 반드시 "•"로 구분하세요. 박스 테두리 대시(──)는 넣지 마세요.
- **서술형 지문/제시문(이야기·상황 설명이 테두리 박스 안에 있는 경우)은 그 본문 전체를
  절대 누락하지 말고**, 하나의 text 블록에 `<조건>` 머리를 붙여 담으세요(박스로 렌더됨).
  예: {"type":"text","value":"<조건> 독수리들이 하늘 높이 날다가 ... (지문 전문) ... 같게 되지."}
  지문 안의 따옴표 대화·문장도 빠짐없이. (지문은 발문/질문 문장과 **분리된 별도 text 블록**.)

## 조건 박스·표 (매우 중요!)
- 테두리/박스 안의 내용(조건, 정의 등)은 **절대 누락하지 마세요.**
- 박스 안에 (가), (나) 등이 있으면 sub_questions로 처리.
- 표(격자/그리드)가 있으면 type="table"로 추출:
```json
{"type": "table", "value": "", "rows": [
  ["열1", "열2", "열3"],
  ["값1", "값2", "값3"],
  ["값4", "값5", "값6"]
]}
```
- 표 안의 수식은 LaTeX로 변환하여 셀에 넣으세요.

## 그림/도형 (figure) — 매우 중요!
- 함수 그래프, 수직선, 좌표평면, 기하 도형, 통계 그래프(막대/히스토그램/꺾은선/원), 사진 등
  **시각 요소가 있으면 그 위치의 contents 에 figure 블록 하나**를 넣으세요:
  {"type":"figure","value":"<도형 종류 + 핵심 수치 한 줄 설명>","bbox":[x0,y0,x1,y1]}
- **bbox** = 지금 보고 있는 이미지 기준 **0~1 정규화** [좌, 상, 우, 하]. 그림 전체를
  **여유 있게 완전히 감싸도록**(라벨·축·화살표·꼭지점 포함) 잡으세요. **절대 잘리면 안 됨** —
  애매하면 **더 크게**. 특히 상단(좌표축/도형 꼭대기)이 잘리지 않게 y(상)을 충분히 위로.
  모르면 bbox 생략 가능(전체로 처리됨).
- value 예: "이차함수 y=x^2-2x-3 그래프, x절편 -1,3 / 꼭짓점 (1,-4)" 또는
  "수직선 -3~5, -1 열린점 / 2 닫힌점 / 사이 강조".
- **같은 그림을 text 로 또 설명하지 마세요.** figure 블록 하나로만 표기(중복 금지).
- **벡터화 불가**(실제 사진·인물·역사적 그림·회화)는 value 를 "[photo] ..." 로 시작.
- **선택지가 그림**인 경우(①~⑤ 가 각각 그래프/도형)도 각 choice 의 contents 에 figure
  블록을 넣으세요(흔함). 각 선택지 bbox 는 그 선택지 그림 영역.
- **figure 가 아닌 것(매우 중요)**: 숫자·수식이 칸/박스에 **나열**된 것(수열·규칙 예시
  "−2, +3, +5, …", 값 표, 보기 박스의 항목 등)은 figure 가 **아닙니다.** 이런 건
  **type="table"** 로(각 칸을 셀로, 수식은 LaTeX) 또는 일반 text/equation 으로 주세요.
  figure 는 **좌표평면·함수그래프·수직선·기하도형(전개도 포함)·통계차트·실제그림**처럼
  *그림으로 그려야만 하는* 것에만 씁니다. 숫자 나열은 표/수식으로 충분합니다.

## 강조 표시
- 밑줄 강조 텍스트: __텍스트__ 형식으로 감싸세요.
  예: {"type":"text","value":"옳지 __않은__ 것은?"}

## 한글 정확도
- 한글의 **모든 음절을 빠짐없이** 추출. 글자를 누락·치환하면 안 됩니다.
- 조사(은/는/이/가/을/를/의)와 접미사(들, 째, 개)를 빠뜨리지 마세요.
- 숫자·분수를 한글로 오인식하지 마세요: "1.1" ≠ "기", \\frac{1}{5} ≠ "다"

## 서술형 문제
- 서술형은 choices를 빈 배열로.
- "(단, 풀이 과정을 반드시 적으시오.)" 등의 부가 지시문도 빠짐없이 추출.
- 그림/도형이 있으면 위 "그림/도형 (figure)" 규칙대로 type="figure" 블록으로 표기.

## 주의사항
- 배점이 있으면 score에 숫자로 기록.
- 이미지에 문제가 여러 개 있으면 모두 추출.
- **이미지의 모든 텍스트를 빠짐없이 추출하세요.**
"""


class OCREngine:
    """Claude Vision API 기반 OCR 엔진."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or get_api_key()
        self.client = anthropic.Anthropic(api_key=self.api_key)

    def _stream_message(self, content: list, max_tokens: int):
        """스트리밍으로 메시지를 생성하고 최종 Message 를 반환한다.

        **논스트리밍(create) 은 max_tokens 가 커서 10분 초과 가능성이 있으면 SDK 가
        "Streaming is required for operations that may take longer than 10 minutes"
        예외를 던진다**(밀집 문항 재시도에서 max_tokens 를 32768 로 올릴 때 발생 —
        2026-06-05). 스트리밍은 이 제한이 없다. `.content`/`.stop_reason` 동일.
        """
        with self.client.messages.stream(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": content}],
        ) as stream:
            return stream.get_final_message()

    def recognize_page(self, image: Image.Image) -> dict:
        """한 페이지 이미지에서 텍스트+수식 추출.

        Args:
            image: 페이지 이미지 (PIL Image)

        Returns:
            구조화된 OCR 결과 dict
        """
        base64_image = image_to_base64(image, format="PNG")
        # 프롬프트 앞배치 + 캐싱(②). 페이지 OCR 도 동일 프롬프트라 캐시 적중.
        content = [
            {"type": "text", "text": EXAM_OCR_PROMPT,
             "cache_control": {"type": "ephemeral"}},
            {"type": "image", "source": {"type": "base64",
                                         "media_type": "image/png", "data": base64_image}},
        ]

        message = self._stream_message(content, OCR_MAX_TOKENS)
        try:
            return self._extract_json(message.content[0].text)
        except json.JSONDecodeError as e:
            # JSON 파싱 완전 실패 시 1회 재시도
            logger.warning("JSON 파싱 실패 (1차), 재시도: %s", e)
            message2 = self._stream_message(content, OCR_MAX_TOKENS)
            return self._extract_json(message2.content[0].text)

    def recognize_crop(self, image: Image.Image) -> dict:
        """크롭(잘라낸 단일 문제 영역) 이미지를 OCR.

        recognize_page 와 동일 스키마({header, questions:[...]})를 반환하되,
        이미지가 보통 문제 1개임을 모델에 알려 경계 혼동을 줄인다.
        """
        base64_image = image_to_base64(image, format="PNG")
        prompt = (
            "이 이미지는 시험지에서 잘라낸 **단일 문제 영역**입니다. "
            "보통 문제 1개(번호·본문·선택지·딸린 그림/표 포함)만 들어 있습니다. "
            "잘린 옆 문제의 일부가 가장자리에 보여도 무시하고, 중심 문제 하나만 추출하세요.\n\n"
            + EXAM_OCR_PROMPT
        )
        # 프롬프트를 **앞**(안정 prefix)에 두고 캐싱(②) — 모든 크롭이 동일 프롬프트라
        # 캐시 적중. 이미지는 캐시 경계 뒤(크롭마다 다름). 입력토큰·지연 대폭 절감.
        content = [
            {"type": "text", "text": prompt,
             "cache_control": {"type": "ephemeral"}},
            {"type": "image", "source": {"type": "base64",
                                         "media_type": "image/png", "data": base64_image}},
        ]

        def _call(max_toks: int):
            return self._stream_message(content, max_toks)

        message = _call(OCR_MAX_TOKENS)
        # 응답 잘림(max_tokens) → JSON 이 깨져 복구 불가 → 더 큰 예산으로 1회 재시도.
        if getattr(message, "stop_reason", None) == "max_tokens":
            logger.warning("크롭 OCR 응답 잘림(max_tokens=%d) → 재시도", OCR_MAX_TOKENS)
            message = _call(min(OCR_MAX_TOKENS * 2, 32768))
            if getattr(message, "stop_reason", None) == "max_tokens":
                raise ValueError(
                    f"OCR 응답이 max_tokens({OCR_MAX_TOKENS * 2})로 잘렸습니다 — "
                    f"수식이 매우 많은 문항(크롭을 더 작게 나눠 보세요)")
        try:
            return self._extract_json(message.content[0].text)
        except json.JSONDecodeError as e:
            # 구조적 깨진 JSON(예: `"value", "value":` ←콜론 누락)은 복구 단계로 못 고친다.
            # 모델이 한 번 더 생성하면 정상 JSON 을 주는 경우가 많아 OCR 자체를 1회 재호출
            # (밀집 문항이 통째로 누락되던 문제 — 2026-06-05 Q8 사례).
            logger.warning("크롭 OCR JSON 파싱 실패 → OCR 재호출 1회: %s", e)
            message = _call(min(OCR_MAX_TOKENS * 2, 32768))
            return self._extract_json(message.content[0].text)

    def _extract_json(self, text: str) -> dict:
        """응답에서 JSON 추출 (LaTeX 수식이 포함된 경우도 처리).

        LLM이 반환하는 JSON은 LaTeX 역슬래시, 이스케이프 누락 등으로
        파싱 실패가 빈번합니다. 여러 단계의 복구를 시도합니다.
        """

        # ── 1단계: JSON 블록 추출 ──
        text = text.strip()

        # ```json ... ``` 블록 처리
        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start)
            text = text[start:end].strip()
        elif "```" in text:
            start = text.index("```") + 3
            end = text.index("```", start)
            text = text[start:end].strip()

        # { 로 시작하는 JSON 찾기
        if not text.startswith("{"):
            brace_start = text.find("{")
            if brace_start != -1:
                text = text[brace_start:]

        # trailing comma 제거
        text = re.sub(r",\s*([}\]])", r"\1", text)

        # ── 1.5단계: LaTeX-JSON 이스케이프 충돌 방지 ──
        # \f(rac), \b(eta), \n(eq), \r(ight), \t(imes) 등은
        # JSON 이스케이프(\f=form-feed, \b=backspace 등)와 충돌하므로
        # LaTeX 명령어인 경우(\+알파벳 연속) 이중 이스케이프로 보호
        text = re.sub(r'(?<!\\)\\([bfnrt])(?=[a-zA-Z])', r'\\\\\1', text)

        # ── 2단계: 직접 파싱 ──
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # ── 3단계: 문자열 내부 역슬래시 이스케이프 복구 ──
        fixed = self._fix_json_backslashes(text)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass

        # ── 4단계: 문자열 값을 보호하면서 구조 복구 ──
        logger.warning("JSON 파싱 실패, 문자열 보호 복구 시도")
        repaired = self._repair_json_strings(text)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass

        # ── 5단계: 줄 단위 복구 (최후 수단) ──
        # 4단계 복구 결과를 토대로, 한 줄짜리 "키": "값" 형태에서 값 안의
        # 이스케이프 안 된 큰따옴표를 보정한다("value" 뿐 아니라 모든 키 대상).
        logger.warning("JSON 파싱 재실패, 줄 단위 복구 시도")
        lines = repaired.split("\n")
        for i, line in enumerate(lines):
            # ^  "키": "  …값…  "  ,?  $   (값이 한 줄 안에서 닫히는 경우만)
            match = re.match(r'^(\s*"[^"]+"\s*:\s*")(.*)("\s*,?\s*)$', line)
            if match:
                inner = match.group(2)
                inner = inner.replace('\\"', '\x00')
                inner = inner.replace('"', '\\"')
                inner = inner.replace('\x00', '\\"')
                lines[i] = match.group(1) + inner + match.group(3)

        text = "\n".join(lines)
        text = re.sub(r",\s*([}\]])", r"\1", text)
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            # 모든 복구 실패 — 호출부(recognize_crop 등)에서 격리해 변환을
            # 중단하지 않도록 명확한 예외로 올린다. 원문 일부를 로그로 남김.
            logger.error("JSON 복구 최종 실패: %s\n원문 앞부분:\n%s",
                         e, text[:800])
            raise

    @staticmethod
    def _fix_json_backslashes(text: str) -> str:
        """JSON 문자열 내부의 이스케이프 안 된 역슬래시를 수정 (1차 시도).

        전체 텍스트에서 \\X (X가 유효 JSON 이스케이프가 아닌 것)를 \\\\X로 변환.
        JSON 구조 바깥에는 역슬래시가 없으므로 전체 텍스트에 적용해도 안전.
        """
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
        # \u는 유지 (\uXXXX 유니코드 이스케이프일 수 있으므로 — 4단계에서 정밀 처리)
        return re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', text)

    @staticmethod
    def _repair_json_strings(text: str) -> str:
        """JSON 문자열 값 내부의 깨진 부분을 복구.

        문자열 리터럴을 하나씩 추출하면서:
        - 유효하지 않은 이스케이프(\\frac, \\{ 등)를 이중 이스케이프
        - \\u + 비16진수를 이중 이스케이프 (\\underset 등 LaTeX)
        - 문자열 내 줄바꿈/탭을 이스케이프
        - 내부 따옴표를 감지하여 이스케이프
        """
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)

        result = []
        i = 0
        while i < len(text):
            if text[i] == '"':
                j = i + 1
                parts = []
                while j < len(text):
                    ch = text[j]
                    if ch == '\\' and j + 1 < len(text):
                        nc = text[j + 1]
                        if nc == 'u':
                            # \uXXXX 유니코드 이스케이프 검증
                            hex_part = text[j + 2:j + 6]
                            if (len(hex_part) == 4
                                    and all(c in '0123456789abcdefABCDEF'
                                            for c in hex_part)):
                                parts.append('\\u')
                                parts.append(hex_part)
                                j += 6
                            else:
                                # \underset 등 LaTeX → 이중 이스케이프
                                parts.append('\\\\u')
                                j += 2
                        elif nc in '"\\/bfnrt':
                            parts.append(ch)
                            parts.append(nc)
                            j += 2
                        else:
                            # \frac, \{ 등 → 이중 이스케이프
                            parts.append('\\\\')
                            parts.append(nc)
                            j += 2
                        continue
                    if ch == '"':
                        # 진짜 문자열 끝인지 확인
                        k = j + 1
                        while k < len(text) and text[k] in ' \t\r\n':
                            k += 1
                        if k >= len(text) or text[k] in ',}]:"':
                            break  # 구조 문자 → 진짜 끝
                        # 내부 따옴표 → 이스케이프
                        parts.append('\\"')
                        j += 1
                        continue
                    if ch == '\n':
                        parts.append('\\n')
                        j += 1
                        continue
                    if ch == '\r':
                        j += 1
                        continue
                    parts.append(ch)
                    j += 1

                result.append('"')
                result.append(''.join(parts))
                result.append('"')
                i = j + 1
            else:
                result.append(text[i])
                i += 1

        return ''.join(result)

    def validate_api_key(self) -> bool:
        """API 키 유효성 검사."""
        try:
            self.client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=10,
                messages=[{"role": "user", "content": "test"}],
            )
            return True
        except anthropic.AuthenticationError:
            return False
        except Exception:
            return True  # 인증 외 오류는 키 자체는 유효할 수 있음


def validate_ocr_response(ocr_result: dict) -> OCRQuality:
    """OCR 응답의 유효성을 검증.

    Args:
        ocr_result: OCR 엔진이 반환한 dict

    Returns:
        OCRQuality 검증 결과
    """
    quality = OCRQuality()

    # 1) 기본 구조 검증
    if not isinstance(ocr_result, dict):
        quality.valid = False
        quality.warnings.append("OCR 응답이 dict가 아닙니다.")
        return quality

    questions = ocr_result.get("questions", [])
    quality.question_count = len(questions)

    # 2) 문제 0개 → 경고
    if quality.question_count == 0:
        quality.warnings.append("인식된 문제가 없습니다. 이미지를 확인하세요.")

    # 3) 수식 개수 집계 + LaTeX 괄호 짝 검증
    for q in questions:
        _validate_question_latex(q, quality)

    return quality


def _validate_question_latex(q_data: dict, quality: OCRQuality) -> None:
    """문제 내 LaTeX 수식의 괄호 짝을 검증."""
    for block in q_data.get("contents", []):
        if block.get("type") in ("equation", "equation_block"):
            quality.equation_count += 1
            _check_latex_brackets(block.get("value", ""), quality)

    for choice in q_data.get("choices", []):
        for block in choice.get("contents", []):
            if block.get("type") in ("equation", "equation_block"):
                quality.equation_count += 1
                _check_latex_brackets(block.get("value", ""), quality)

    for sub in q_data.get("sub_questions", []):
        _validate_question_latex(sub, quality)


def _check_latex_brackets(latex: str, quality: OCRQuality) -> None:
    """LaTeX 문자열의 중괄호 짝이 맞는지 확인."""
    depth = 0
    for ch in latex:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        if depth < 0:
            quality.warnings.append(
                f"LaTeX 괄호 불일치 (닫는 괄호 초과): {latex[:50]}..."
            )
            return
    if depth != 0:
        quality.warnings.append(
            f"LaTeX 괄호 불일치 (여는 괄호 {depth}개 초과): {latex[:50]}..."
        )
