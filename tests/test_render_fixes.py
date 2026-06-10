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
from core.hwp_com_writer import (_is_table_caption, _is_value_box, _shade_target_mode,
                                 _is_labelless_box)
from core.hwp_form_writer import _essay_label_and_body, _adaptive_columns
from models.exam_document import ContentBlock, ContentType as CT


def _tb(val):
    return ContentBlock(type=CT.TEXT, value=val)


def _eq(val):
    return ContentBlock(type=CT.EQUATION, value=val)


def _table():
    return ContentBlock(type=CT.TABLE, value="", rows=[["a", "b"], ["1", "2"]])


class _FakeHwp:
    def GetPos(self):
        return (0, 0, 0)


class _FakeSession:
    """COM 없이 _write_condition_box 분기만 도는 무동작 세션."""

    def __init__(self):
        self.hwp = _FakeHwp()

    def __getattr__(self, name):          # align_*/table_*/break_para 등 전부 no-op
        return lambda *a, **k: None


def _box_calls(blocks):
    """_write_condition_box 를 스텁 위에서 실행 — 무한재귀(C1)면 RecursionError."""
    w = W.HwpComWriter.__new__(W.HwpComWriter)
    w.s = _FakeSession()
    written = []
    w._write_block = lambda b: written.append(b.type)
    w._write_box_content = lambda blocks, space_values=False: None
    w._write_condition_box(blocks)
    return written


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

    # ── R3: 라벨 없는 셀 가운데정렬(#14) — _is_labelless_box ──
    # 항목 라벨((가)(나)/ㄱ.)·불릿(•) 없는 <상자>(단일 진술)는 가운데, 라벨/불릿 박스는 좌측.
    labelless = [_tb("<상자> 모든 자연수 "), _eq("n"), _tb("에 대하여 "), _eq("2a_n+S_n=k"), _tb("이다.")]
    bullet_box = [_tb("<상자> (가) "), _eq("a_6=32"), _tb(" • (나) 모든 자연수 "), _eq("n")]
    chk(_is_labelless_box(labelless), "라벨없는 진술상자(#14)=가운데")
    chk(not _is_labelless_box(bullet_box), "(가)(나)불릿 박스는 라벨없음 아님(좌측)")
    chk(not _is_labelless_box(bogi_box), "<보기>박스는 라벨없음 아님(좌측)")

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

    # ── G: 박스↔표 혼합 분기(C1 무한재귀 회귀) ──
    hdr = _tb("<보기> ㄱ. ")
    try:
        # 패턴1: 머리 **뒤** 표(_recover_table append 모양) — 과거 무한재귀 크래시
        w1 = _box_calls([hdr, _eq("a"), _table()])
        chk(w1 == [CT.TABLE], f"머리뒤 표는 박스 밖 개별 렌더: {w1}")
        # 패턴2: 표 뒤 머리(#18 z-표 경로, 기존 동작 유지)
        w2 = _box_calls([_table(), hdr, _eq("a")])
        chk(w2 == [CT.TABLE], f"표뒤 머리: 표만 개별 렌더: {w2}")
        # 패턴3: 표가 앞뒤 양쪽
        w3 = _box_calls([_table(), hdr, _eq("a"), _table()])
        chk(w3 == [CT.TABLE, CT.TABLE], f"앞뒤 표 모두 개별 렌더: {w3}")
        # 패턴4: 머리 없는 표만 — 전부 개별 렌더(기존 동작)
        w4 = _box_calls([_table(), _eq("a")])
        chk(w4 == [CT.TABLE, CT.EQUATION], f"머리 없음→전부 개별: {w4}")
    except RecursionError:
        chk(False, "C1 무한재귀 재발(_write_condition_box)")

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

    # ── G: overline(bar) 앞 공백 — 상인고 #24 ──
    # ``2i\overline{z}`` 가 ``2ibar`` literal 로 새던 회귀(HWP accent 키워드가 앞 글자에 붙음).
    # bar 앞이 영숫자면 공백을 보장해 ``2i bar {z}`` 로 분리돼야 한다(단독 \overline 은 정상).
    from core.latex_to_hwpeq import latex_to_hwpeq
    g1 = latex_to_hwpeq(r"2i\overline{z}")
    chk("2ibar" not in g1 and "bar" in g1, f"G overline 앞공백: {g1!r}")
    g2 = latex_to_hwpeq(r"(4+3i)z+2i\overline{z}=5+i")
    chk("2ibar" not in g2, f"G overline 식중간: {g2!r}")

    # ── I: bigstar(★) 마커 — 상인고 수1 #12 ──
    # ``\bigstar`` 가 SYMBOL_MAP 에 없어 통째 증발 → ``(★)`` 이 ``()`` 로 새던 회귀.
    # □(\square)처럼 따옴표 리터럴 ★ 로 매핑돼야 한다.
    i1 = latex_to_hwpeq(r"\cdots\cdots (\bigstar)")
    chk("★" in i1, f"I bigstar 매핑: {i1!r}")

    # ── L: rm/bold 키워드 앞 공백 — 매천중 #7·#18 (PLEFT 계열) ──
    # ``x\mathrm{km}`` 이 ``xrm km`` 으로 붙어 HWP 가 xrm literal 렌더하던 회귀.
    l1 = latex_to_hwpeq(r"x\mathrm{km}")
    chk("xrm" not in l1 and "x rm km" in l1, f"L rm 앞공백: {l1!r}")
    l2 = latex_to_hwpeq(r"400\mathrm{m}")
    chk("400 rm m" in l2 or "400rm" not in l2, f"L 숫자 뒤 rm: {l2!r}")

    # ── M: <조건> 박스 머리 vs 인라인 참조 — 매천중 #19 소문항 조건박스 ──
    # ``<조건> 한 미지수…``(공백+한글=박스 내용)는 머리, ``<조건>을``(조사 직결)은 참조.
    from core.hwp_com_writer import _COND_HEADER_RE
    chk(bool(_COND_HEADER_RE.search("<조건> 한 미지수에 대한 식")), "M 조건+공백+한글=박스 머리")
    chk(not _COND_HEADER_RE.search("<조건>을 사용하여"), "M 조건+조사=인라인 참조")
    chk(not _COND_HEADER_RE.search("<보기>에서 고르시오"), "M 보기+조사=인라인 참조")

    # ── J: \boxed → BOX{} 테두리 박스 — 상인고 수1 #12 빈칸채우기 (가)/(나)/(다) ──
    # ``\boxed{가}`` → ``BOX{ ~ ㈎ ~ }``(작은 박스). BOX 가 rm 으로 감싸이면 "BOX" 글자로
    # 깨지므로 _roman_skip 에 BOX 가 있어야 한다(rm {BOX} 금지).
    j1 = latex_to_hwpeq(r"\boxed{가}")
    chk("BOX{" in j1 and "㈎" in j1 and "rm {BOX}" not in j1, f"J boxed 가: {j1!r}")
    j2 = latex_to_hwpeq(r"2 - \frac{1}{k} + \boxed{나} < \boxed{다}")
    chk(j2.count("BOX{") == 2 and "㈏" in j2 and "㈐" in j2, f"J boxed 식중간: {j2!r}")

    # ── R4: 거대 문항 단독 단 배치(_adaptive_columns solo) — 상인고 수1 #12 ──
    # 거대 문항(solo 인덱스)은 앞 단을 닫고 자기 단에 혼자, 다음 문항은 새 단에서 시작.
    # 일반 문항(짧음)은 3/단 그대로. (heights 작아도 solo 면 단독.)
    hs = {i: 8 for i in range(6)}            # 6문항 모두 짧음(8줄)
    _, _, cols0 = _adaptive_columns(hs, 6, 3)                 # solo 없음 → 3,3
    chk([len(c) for c in cols0] == [3, 3], f"R4 solo없음 3/단: {[len(c) for c in cols0]}")
    _, _, cols1 = _adaptive_columns(hs, 6, 3, solo={2})       # Q2 단독
    chk([2 in c and len(c) == 1 for c in cols1].count(True) == 1
        and any(c == [2] for c in cols1), f"R4 Q2 단독 단: {cols1}")
    chk(all(2 not in c for c in cols1 if c != [2]), f"R4 Q2 다른단 미혼입: {cols1}")

    # ── H: 서술형 라벨 번호 결정적 재부여 — 상인고 #25(정답면 [서술형 5]→6) ──
    # grow 가 마지막 답지 라벨을 5(6이어야)로 굽고 COM 비결정으로 본문/정답이 뒤바뀜.
    # _renumber_essay_labels 가 문서순 (본문,정답) 쌍을 1,1,…,n,n 으로 결정적 고정.
    import re as _re, zipfile, tempfile, os
    from core.hwp_form_writer import _renumber_essay_labels, _ESSAY_LABEL_NUM_RE
    def _lbl(n):  # [서술형 N] 라벨 한 개의 XML
        return (f'<hp:t> [서술형 </hp:t><hp:equation id="1" version="Equation Version 60">'
                f'<hp:script>{n}</hp:script></hp:equation><hp:t>]</hp:t>')
    # 본문6,정답5,정답6 누락된 비결정 케이스: [1,1,2,2,3,3,4,4,5,5,5,6]
    nums = [1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 5, 6]
    sec = "<hp:sec>" + "".join(_lbl(n) for n in nums) + "</hp:sec>"
    fd, tmp = tempfile.mkstemp(suffix=".hwpx")
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp, "w") as z:
            z.writestr("Contents/section0.xml", sec)
        changed = _renumber_essay_labels(tmp, 6)
        with zipfile.ZipFile(tmp) as z:
            got = z.read("Contents/section0.xml").decode("utf-8")
        out = [m.group(2) for m in _ESSAY_LABEL_NUM_RE.finditer(got)]
        chk(out == ["1", "1", "2", "2", "3", "3", "4", "4", "5", "5", "6", "6"],
            f"H 라벨 재부여: {out} (changed={changed})")
        # 라벨 수 불일치(7개)면 건드리지 않음(오손상 방지)
        sec2 = "<hp:sec>" + "".join(_lbl(n) for n in [1, 1, 2, 2, 3, 3, 7]) + "</hp:sec>"
        with zipfile.ZipFile(tmp, "w") as z:
            z.writestr("Contents/section0.xml", sec2)
        chk(_renumber_essay_labels(tmp, 6) == 0, "H 라벨수 불일치→재부여 생략")
    finally:
        os.remove(tmp)

    # ── K: 서술형·단답형 혼합 라벨 — 능인고 수1(16~18 서술형, 19~20 단답형) ──
    # ① _DUP_LABEL_RE 가 단답형 중복도 잡고 ② _renumber_essay_labels(words=) 가 정답 라벨을
    # 문항별 유형으로 맞춘다(폼 정답라벨은 전부 [서술형]뿐).
    from core.hwp_form_writer import _DUP_LABEL_RE, _renumber_essay_labels as _renum
    chk(_DUP_LABEL_RE.search("[단답형 4][단답형 4]") is not None, "K _DUP 단답형 중복 매칭")
    chk(_DUP_LABEL_RE.search("[서술형 4][단답형 4]") is not None, "K _DUP 혼합 중복 매칭")

    def _lblw(word, n):
        return (f'<hp:t> [{word} </hp:t><hp:equation id="1" version="x">'
                f'<hp:script>{n}</hp:script></hp:equation><hp:t>]</hp:t>')
    # 정답 라벨이 전부 서술형(폼 native)인 5쌍 — 본문유형 [서술,서술,서술,단답,단답] 로 맞춰야.
    sec3 = "<hp:sec>" + "".join(_lblw("서술형", n) for n in [1, 1, 2, 2, 3, 3, 4, 4, 5, 5]) + "</hp:sec>"
    fd2, tmp2 = tempfile.mkstemp(suffix=".hwpx"); os.close(fd2)
    try:
        with zipfile.ZipFile(tmp2, "w") as z:
            z.writestr("Contents/section0.xml", sec3)
        _renum(tmp2, 5, words=["서술형", "서술형", "서술형", "단답형", "단답형"])
        with zipfile.ZipFile(tmp2) as z:
            g = z.read("Contents/section0.xml").decode("utf-8")
        words_out = _re.findall(r"\[(서술형|서답형|단답형)\s*</hp:t>", g)
        chk(words_out == ["서술형", "서술형", "서술형", "서술형", "서술형", "서술형",
                          "단답형", "단답형", "단답형", "단답형"],
            f"K 혼합 라벨 단어 per-essay: {words_out}")
    finally:
        os.remove(tmp2)

    if fails:
        print("FAIL test_render_fixes:")
        print("\n".join(fails))
        return 1
    print("OK test_render_fixes (cell/value-box/caption/shading/essay-label/overline/relabel/bigstar/boxed/labelless/solo/mixed-label/rm-space/cond-header)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
