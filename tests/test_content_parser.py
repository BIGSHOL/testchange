# content_parser 후보정 회귀 단위테스트 (stdlib only, API·키 0).
#   python tests/test_content_parser.py
#
# 현재 커버: 한글↔숫자 띄어쓰기(_space_hangul_before_eq) + 서수 접두사 '제' 예외.
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from core.content_parser import parse_ocr_response
from models.exam_document import ContentType


def _render(text: str) -> str:
    """발문 텍스트 하나를 파서에 통과시켜, 텍스트/수식을 평문으로 직렬화."""
    doc = {"header": "", "questions": [{"number": 1, "contents": [{"type": "text", "value": text}]}]}
    q = parse_ocr_response(doc, page_number=1).questions[0]
    out = []
    for b in q.contents:
        if b.type == ContentType.TEXT:
            out.append(b.value or "")
        else:
            out.append((b.value or "").strip())  # 수식은 값만(숫자/기호)
    return "".join(out)


# (입력, 직렬화 결과에 **반드시 포함**돼야 하는 부분문자열) — 띄어쓰기 검증.
_SPACING_CASES = [
    ("이 시행을36번 반복할 때", "시행을 36번"),    # 조사+숫자 → 띄움
    ("주사위를2번 던질 때", "주사위를 2번"),        # 조사+숫자 → 띄움
    ("제4사분면을 지나지 않는다", "제4사분면"),      # 서수 접두사 '제'+숫자 → 붙임
    ("그림의 제2사분면", "제2사분면"),              # 〃 (문장 중간)
    ("제100항까지", "제100항"),                   # 〃 (여러 자리)
    ("이 문제3을 풀어라", "문제 3"),               # '제'가 단어 끝 음절(문제) → 띄움
    ("과제3을 제출", "과제 3"),                    # 〃 (과제)
]


def run():
    fails = []
    for text, must in _SPACING_CASES:
        got = _render(text)
        if must not in got:
            fails.append(f"  띄어쓰기: {text!r} → {got!r} (기대 포함: {must!r})")
    if fails:
        print("FAIL test_content_parser:")
        print("\n".join(fails))
        return 1
    print(f"OK test_content_parser ({len(_SPACING_CASES)} cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
