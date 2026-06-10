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


def _parse_q(text: str, score=None):
    doc = {"header": "", "questions": [{"number": 1, "score": score,
                                        "contents": [{"type": "text", "value": text}]}]}
    return parse_ocr_response(doc, page_number=1).questions[0]


# (입력 텍스트, OCR score 필드, 기대 score) — 배점 캡처(소수·총점) 검증. 본문에선 제거돼야 함.
_SCORE_CASES = [
    ("다음을 구하시오. [4.5점]", None, 4.5),    # 소수 배점: 캡처 없이 삭제되던 버그(M1)
    ("다음을 구하시오. [총 7점]", None, 7),     # 부모 총점: split 후 소실되던 버그(M2)
    ("다음을 구하시오. [3점]", None, 3),        # 기존 정수 경로 유지
    ("다음을 구하시오. [4점]", 5, 5),           # score 필드 우선(본문 캡처 안 함)
]


def _parse_eq_blocks(value: str):
    """equation 블록 하나를 파서에 통과시켜 (type,value) 리스트로."""
    doc = {"header": "", "questions": [{"number": 1, "contents": [
        {"type": "equation", "value": value}]}]}
    q = parse_ocr_response(doc, page_number=1).questions[0]
    return [(b.type, (b.value or "")) for b in q.contents]


# B-1(상인고 #14): 복소수 상수 + 그리스 변수 근 나열 ``2-3i, \alpha, \beta`` 의 쉼표가
# 스푸리어스-쉼표 방어에 뭉개져 ``2-3i \alpha \beta`` 로 합쳐지던 회귀. 쉼표(텍스트)가
# 항목 사이에 보존돼야(개별 수식 + 텍스트 ", ").
def _check_comma_roots(fails):
    blocks = _parse_eq_blocks(r"2-3i, \alpha, \beta")
    eqs = [v for t, v in blocks if t == ContentType.EQUATION]
    texts = "".join(v for t, v in blocks if t == ContentType.TEXT)
    if len(eqs) < 3 or "," not in texts:
        fails.append(f"  B-1 근나열 쉼표: {blocks!r} (기대: 개별수식 3+ & 텍스트 쉼표)")


def run():
    fails = []
    _check_comma_roots(fails)
    for text, must in _SPACING_CASES:
        got = _render(text)
        if must not in got:
            fails.append(f"  띄어쓰기: {text!r} → {got!r} (기대 포함: {must!r})")
    for text, field, want in _SCORE_CASES:
        q = _parse_q(text, score=field)
        if q.score != want:
            fails.append(f"  배점 캡처: {text!r}(score={field}) → {q.score!r} (기대 {want!r})")
        body = "".join((b.value or "") for b in q.contents)
        if "점]" in body:
            fails.append(f"  배점 잔존: {text!r} → 본문에 남음: {body!r}")
    if fails:
        print("FAIL test_content_parser:")
        print("\n".join(fails))
        return 1
    print(f"OK test_content_parser ({len(_SPACING_CASES) + len(_SCORE_CASES) + 1} cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
