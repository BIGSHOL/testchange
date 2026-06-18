# _extract_json 견고성 회귀 테스트 (stdlib·API·키 0).
#   python tests/test_extract_json.py
#
# 커버: 닫는 ``` 펜스 없는 잘린 응답(ValueError 크래시 → find 폴백, 2026-06-10 감사 M13),
#        기존 정상 경로(펜스/비펜스/트레일링 콤마) 무회귀.
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from core.ocr_engine import OCREngine


def _engine():
    return OCREngine.__new__(OCREngine)   # 클라이언트 없이 파서만(키 불필요)


def run():
    e = _engine()
    fails = []

    def chk(cond, msg):
        if not cond:
            fails.append("  " + msg)

    # 닫는 펜스 없음(잘린 응답) — 과거 text.index() ValueError 로 페이지째 크래시
    try:
        r = e._extract_json('```json\n{"questions": [{"number": 1}]}')
        chk(r.get("questions", [{}])[0].get("number") == 1, "펜스 미닫힘: 내용 파싱")
    except ValueError as ex:
        chk(False, f"펜스 미닫힘이 여전히 크래시: {ex}")
    # 정상 경로 무회귀
    chk(e._extract_json('```json\n{"a": 1}\n```') == {"a": 1}, "json 펜스 정상")
    chk(e._extract_json('```\n{"a": 1}\n```') == {"a": 1}, "무명 펜스 정상")
    chk(e._extract_json('앞말 {"a": [1, 2,]} ') == {"a": [1, 2]}, "비펜스+트레일링 콤마")

    # Extra data(경상여고 미적1, 2026-06-18): 유효 객체 뒤에 데이터가 더 붙으면 json.loads 가
    # "Extra data" 로 실패해 크롭째 건너뛰던 것 — raw_decode 로 첫 객체만 취하고 후행은 버린다.
    chk(e._extract_json('{"questions": [{"number": 7}]}\n{"junk": 1}')
        .get("questions", [{}])[0].get("number") == 7, "Extra data: 후행 객체 무시")
    chk(e._extract_json('{"a": 1}  설명 텍스트') == {"a": 1}, "Extra data: 후행 텍스트 무시")
    chk(e._extract_json('```json\n{"a": 1}\n```\n추가 설명') == {"a": 1}, "펜스+후행 텍스트")

    if fails:
        print("FAIL test_extract_json:")
        print("\n".join(fails))
        return 1
    print("OK test_extract_json (fence-fallback/normal paths)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
