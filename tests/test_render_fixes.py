# 강동중 8건 렌더 수정의 결정적 헬퍼 회귀 단위테스트 (stdlib·HWP COM·API·키 0).
#   python tests/test_render_fixes.py
#
# 커버: 표 셀 분류(_write_cell 분기 규칙)·값상자 판정(_is_value_box)·표제목 캡션(_is_table_caption)·
#        z-표 음영 시그니처(_shade_target_mode)·비괄호 서술형 라벨(_essay_label_and_body).
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import core.hwp_com_writer as W
from core.hwp_com_writer import _is_table_caption, _is_value_box, _shade_target_mode
from core.hwp_form_writer import _essay_label_and_body
from models.exam_document import ContentBlock, ContentType as CT


def _tb(val):
    return ContentBlock(type=CT.TEXT, value=val)


def _eq(val):
    return ContentBlock(type=CT.EQUATION, value=val)


def _cell_kind(val):
    """_write_cell 의 분기를 순수 판정(text vs equation) — 렌더 호출 없이 규칙만 검증."""
    if not val:
        return "skip"
    if W._HAS_HANGUL_RE.search(val) and "\\" not in val:
        return "text"
    if "\\" in val or " " not in val:
        return "equation"
    return "text"


def run():
    fails = []

    def chk(cond, msg):
        if not cond:
            fails.append("  " + msg)

    # ── A: 셀 분류 ──
    chk(_cell_kind("합계") == "text", "순한글→평문")
    chk(_cell_kind("6이상 ~ 12미만") == "text", "한글범위→평문")
    chk(_cell_kind("유통기한(개월)") == "text", "한글헤더→평문")
    chk(_cell_kind("12 ~ 18") == "text", "숫자범위(공백)→평문")
    chk(_cell_kind("6 8") == "text", "줄기잎 다중값→평문")
    chk(_cell_kind("A") == "equation", "변수 단일토큰→수식")
    chk(_cell_kind("0.16") == "equation", "소수 단일토큰→수식")
    chk(_cell_kind("P(X=x)") == "equation", "함수 단일토큰→수식")
    chk(_cell_kind("\\dfrac{1}{2}") == "equation", "LaTeX→수식")
    chk(_cell_kind("P(0 \\leq Z \\leq z)") == "equation", "LaTeX(공백 포함)→수식")

    # ── C: 값상자 vs 라벨박스 ──
    value_box = [_tb("<상자> "), _eq("18"), _eq("13"), _eq("8"), _eq("13")]
    labeled_box = [_tb("<상자> (가) "), _eq("3x^2"), _tb("(나) "), _eq("x^2")]
    bogi_box = [_tb("<보기> ㄱ. "), _eq("a"), _tb("ㄴ. "), _eq("b")]
    chk(_is_value_box(value_box), "값상자(18 13 …)는 value_box")
    chk(not _is_value_box(labeled_box), "(가)(나) 라벨박스는 value_box 아님")
    chk(not _is_value_box(bogi_box), "<보기>ㄱㄴ 박스는 value_box 아님")

    # ── E: 표제목 캡션 vs 발문 문장 ──
    chk(_is_table_caption("헬스클럽 회원의 나이 (단위:세)"), "표제목=캡션")
    chk(_is_table_caption("어느 마트에서 판매하는 통조림의 유통기한"), "표제목=캡션2")
    chk(not _is_table_caption("확률변수 X의 확률분포를 표로 나타내면 다음과 같다."), "발문(.)은 캡션 아님")
    chk(not _is_table_caption("다음 중 옳은 것은?"), "발문(?)은 캡션 아님")
    chk(not _is_table_caption("위 자료의 평균과 최빈값을 각각 구하시오"), "발문(구하시오)은 캡션 아님")

    # ── D: z-표 음영 시그니처 (헤더에 LEQ Z LEQ 있을 때만 row0) ──
    ztable = ('<hp:tbl rowCnt="4" colCnt="2"><hp:equation>P(0 LEQ Z LEQ z)</hp:equation>'
              '<hp:equation>0.3413</hp:equation></hp:tbl>')
    freq2col = ('<hp:tbl rowCnt="7" colCnt="2"><hp:equation>3</hp:equation>'
                '<hp:equation>5</hp:equation></hp:tbl>')   # 도서 도수분포표(2열, z 아님)
    prob = ('<hp:tbl rowCnt="2" colCnt="4"><hp:equation>P(X=x)</hp:equation>'
            '<hp:equation>1</hp:equation></hp:tbl>')
    chk(_shade_target_mode(ztable) == "row0", "z-표(P(0≤Z≤z))→row0 음영")
    chk(_shade_target_mode(freq2col) is None, "단순 2열 도수분포표→음영 없음(#16 버그)")
    chk(_shade_target_mode(prob) == "col0", "확률분포표(2행≥3열)→col0 음영")

    # ── F: 비괄호 서술형 라벨 제거 + 단어 통일 ──
    # 파싱 후 "서술형 4." = TEXT"서술형 " + EQ"4" + TEXT". 다음은…"
    split_blocks = [_tb("서술형 "), _eq("4"), _tb(". 다음은 헬스클럽 회원")]
    label, body = _essay_label_and_body(split_blocks, "서답형", 4)
    chk(label == "[서술형 4]", f"비괄호 분리형 라벨 통일: {label}")
    chk(body and body[0].value.startswith("다음은"), f"본문에서 '서술형 4.' 제거: {body[0].value if body else None!r}")
    # 한 블록형 "서술형 4. 다음은…"
    one_block = [_tb("서술형 4. 다음은 헬스클럽")]
    label2, body2 = _essay_label_and_body(one_block, "서답형", 4)
    chk(label2 == "[서술형 4]", f"비괄호 한블록 라벨: {label2}")
    chk(body2 and body2[0].value.startswith("다음은"), "한블록 본문 라벨 제거")

    if fails:
        print("FAIL test_render_fixes:")
        print("\n".join(fails))
        return 1
    print("OK test_render_fixes (cell/value-box/caption/shading/essay-label)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
