# 객관식 표 누락 복구(_recover_table) 회귀 단위테스트 (stdlib only, API·키 0).
#   python tests/test_table_recovery.py
#
# 단일 크롭 구조화 OCR 이 확률분포표/정규분포표를 "요약"해 통째 누락할 때,
# 표 지시어 게이트 → 마크다운 전사(_transcribe_table, 여기선 stub) → rows 파싱 →
# questions[0].contents 끝 삽입까지의 **결정적 경로**를 검증한다(전사 호출만 stub).
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from core.ocr_engine import (
    OCREngine,
    _TABLE_HINT_RE,
    _has_table_block,
    _parse_markdown_table,
    _question_text_blob,
)


def _check(cond, msg, fails):
    if not cond:
        fails.append("  " + msg)


def run():
    fails: list[str] = []

    # ── _TABLE_HINT_RE: 표 지시어를 잡고, 무관 텍스트는 안 잡는다 ──
    for hint in ["확률분포를 표로 나타내면", "정규분포표를 이용하여", "표준정규분포표",
                 "P(X=x)", "z의 값은?", "확률변수 X의 확률분포"]:
        _check(_TABLE_HINT_RE.search(hint), f"hint 미검출: {hint!r}", fails)
    for noise in ["정규분포를 따른다.", "다음 중 옳은 것은?", "평균과 표준편차를 구하시오"]:
        _check(not _TABLE_HINT_RE.search(noise), f"noise 오검출: {noise!r}", fails)

    # ── _has_table_block ──
    _check(_has_table_block({"questions": [{"contents": [{"type": "table", "rows": [["a"]]}]}]}),
           "table 블록을 못 찾음", fails)
    _check(not _has_table_block({"questions": [{"contents": [{"type": "text", "value": "x"}]}]}),
           "table 없는데 있다고 함", fails)

    # ── _parse_markdown_table: 구분선 제거·≥2행 요구 ──
    md = "| z | P(0≤Z≤z) |\n|---|---|\n| 1.0 | 0.3413 |\n| 2.0 | 0.4772 |"
    rows = _parse_markdown_table(md)
    _check(rows == [["z", "P(0≤Z≤z)"], ["1.0", "0.3413"], ["2.0", "0.4772"]],
           f"마크다운 파싱 틀림: {rows}", fails)
    _check(_parse_markdown_table("| 단일행 |") == [], "1행짜리는 버려야 함", fails)
    _check(_parse_markdown_table("표 없음") == [], "표 아닌 텍스트는 빈 리스트", fails)

    # ── _recover_table 통합: 표 없음 + 지시어 → stub 전사로 표 삽입 ──
    eng = OCREngine(api_key="dummy")  # anthropic 은 실제 호출 때만 키 검증
    eng._transcribe_table = lambda b64: md  # API 대역(stub)
    result = {"questions": [{
        "number": 3,
        "contents": [{"type": "text", "value": "확률변수 X의 확률분포를 표로 나타내면 다음과 같다."}],
        "choices": [{"number": 1, "contents": [{"type": "text", "value": "1"}]}],
    }]}
    eng._recover_table(result, "ZHVtbXk=")
    inserted = [c for c in result["questions"][0]["contents"] if c.get("type") == "table"]
    _check(len(inserted) == 1, "표가 삽입되지 않음", fails)
    if inserted:
        _check(inserted[0]["rows"][0] == ["z", "P(0≤Z≤z)"], "삽입된 표 내용 틀림", fails)

    # ── 게이트: 이미 표가 있으면 추가 호출 안 함(전사 stub 이 불려도 중복삽입 금지) ──
    called = {"n": 0}
    def _boom(b64):
        called["n"] += 1
        return md
    eng._transcribe_table = _boom
    with_table = {"questions": [{
        "number": 4,
        "contents": [{"type": "text", "value": "확률분포표"},
                     {"type": "table", "rows": [["X", "1"]]}],
    }]}
    eng._recover_table(with_table, "ZHVtbXk=")
    _check(called["n"] == 0, "이미 표 있는데 전사 호출함(비용)", fails)

    # ── 게이트: 지시어 없으면 전사 호출 안 함 ──
    eng._transcribe_table = _boom
    no_hint = {"questions": [{"number": 5,
                              "contents": [{"type": "text", "value": "다음 중 옳은 것은?"}]}]}
    eng._recover_table(no_hint, "ZHVtbXk=")
    _check(called["n"] == 0, "지시어 없는데 전사 호출함(비용)", fails)

    if fails:
        print("FAIL test_table_recovery:")
        print("\n".join(fails))
        return 1
    print("OK test_table_recovery (hint/has_table/parse/recover/gate)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
