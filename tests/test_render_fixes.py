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
    # km 은 단위라 ``x rm`km``(단위 백틱, 2026-06-11) — PLEFT(앞 'xrm' 안 붙음)는 유지.
    l1 = latex_to_hwpeq(r"x\mathrm{km}")
    chk("xrm" not in l1 and "x rm`km" in l1, f"L rm 앞공백+단위백틱: {l1!r}")
    l2 = latex_to_hwpeq(r"400\mathrm{m}")  # m 은 단위 아님(모평균 m 보호) → 백틱 없음
    chk("400 rm m" in l2 or "400rm" not in l2, f"L 숫자 뒤 rm: {l2!r}")

    # ── N: 좌표 단 점 이름 = 점 글자 rm + 좌표 it (도원중 #10·12·23, 2026-06-11) ──
    # HWP rm 은 명시적 it 전까지 뒤 전체로 번지므로, 통째 로만화하면 a,b 까지 로만으로 깨진다.
    from core.content_parser import _romanize_point_names
    geo = _romanize_point_names([_tb("점 "), _eq("P(a, b)"), _tb("가 제3사분면")])
    pv = next(b.value for b in geo if b.type == CT.EQUATION)
    n1 = latex_to_hwpeq(pv, italicize_stat=False)
    chk(pv == r"\mathrm{P}\mathit{(a, b)}" and n1 == "rm P it {(a,~b)}",
        f"N 점 P(a,b) = rm P it: {pv!r} -> {n1!r}")
    # 안전경계: 확통 P(X=r)(비기하) 무변경, 함수 F(x)(쉼표 없음) 무변경.
    stat = _romanize_point_names([_tb("확률변수 X"), _eq("P(X=r)")])
    chk(next(b.value for b in stat if b.type == CT.EQUATION) == "P(X=r)",
        "N 확통 P(X=r) 무변경(비기하)")
    fx = _romanize_point_names([_tb("삼각형"), _eq("F(x)")])
    chk(next(b.value for b in fx if b.type == CT.EQUATION) == "F(x)",
        "N 함수 F(x) 무변경(쉼표 없음)")

    # ── O: \mathit{…} → it {…} 지원 + 변수/숫자 단위 백틱 (2026-06-11) ──
    o1 = latex_to_hwpeq(r"\mathit{(a, b)}", italicize_stat=False)
    chk("it {" in o1, f"O mathit 지원: {o1!r}")
    chk(latex_to_hwpeq(r"a\mathrm{cm}", italicize_stat=False) == "a rm`cm",
        "O 변수+단위 백틱 a cm")
    chk(latex_to_hwpeq(r"5\mathrm{cm}", italicize_stat=False) == "5 rm`cm",
        "O mathrm 숫자+단위 백틱 5 cm")

    # ── M: <조건> 박스 머리 vs 인라인 참조 — 매천중 #19 소문항 조건박스 ──
    # ``<조건> 한 미지수…``(공백+한글=박스 내용)는 머리, ``<조건>을``(조사 직결)은 참조.
    from core.hwp_com_writer import _COND_HEADER_RE
    chk(bool(_COND_HEADER_RE.search("<조건> 한 미지수에 대한 식")), "M 조건+공백+한글=박스 머리")
    chk(not _COND_HEADER_RE.search("<조건>을 사용하여"), "M 조건+조사=인라인 참조")
    chk(not _COND_HEADER_RE.search("<보기>에서 고르시오"), "M 보기+조사=인라인 참조")
    # M2(월암중 #11·상원중 #16): ``<보기> 중 …``(공백+참조어)도 발문 인라인 참조 — 박스로
    # 오인하면 발문이 박스에 갇히고 보기 항목이 평문으로 풀린다. "중간…" 일반 단어는 박스.
    chk(not _COND_HEADER_RE.search("<보기> 중 일차함수"), "M2 보기+중=인라인 참조")
    chk(not _COND_HEADER_RE.search("<보기> 에서 고른"), "M2 보기+에서(공백)=인라인 참조")
    chk(bool(_COND_HEADER_RE.search("<보기> 중간값을 구하라")), "M2 보기+중간…=박스 머리")
    # P(월암중 #9·#19): 폼 경로 밑줄 강조 — _put_block 이 underline TEXT 를 underline_run
    # 으로 찍어야 한다("옳지 않은"·"더하거나 빼어서" 강조 소실 방지). COM 없이 무동작 세션로 검증.
    from core.hwp_form_writer import _put_block as _fpb

    class _USes:
        def __init__(self):
            self.calls = []

        def text(self, s):
            self.calls.append(("text", s))

        def underline_run(self, s):
            self.calls.append(("underline", s))

    _us = _USes()
    _fpb(_us, ContentBlock(type=CT.TEXT, value="더하거나 빼어서", underline=True))
    _fpb(_us, ContentBlock(type=CT.TEXT, value=" 푸시오."))
    chk(_us.calls == [("underline", "더하거나 빼어서"), ("text", " 푸시오.")],
        f"P 폼 밑줄 강조: {_us.calls!r}")

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

    # ── Q: sqrt/root 키워드 영숫자 앞 공백 — 중앙중 중3 #4·#15 (2026-06-11) ──
    # ``a\sqrt{2}`` 가 ``asqrt {2}`` 로 붙으면 HWP 가 "asqrt" 를 식별자로 오인해 literal.
    # 숫자 앞(2\sqrt{2})은 HWP 가 숫자→알파벳 경계를 쪼개 우연히 살았을 뿐 — 글자 앞이 함정.
    from core.latex_to_hwpeq import latex_to_hwpeq as _l2h
    q1 = _l2h(r"a\sqrt{2}+b\sqrt{6}")
    chk("asqrt" not in q1 and "bsqrt" not in q1, f"Q sqrt 글자 앞 공백: {q1}")
    q2 = _l2h(r"(a+b\sqrt{c})\mathrm{cm}^2")
    chk("bsqrt" not in q2, f"Q sqrt 괄호식 안 공백: {q2}")
    q3 = _l2h(r"a\sqrt[3]{8}")
    chk("aroot" not in q3, f"Q root 글자 앞 공백: {q3}")

    # ── R5: 선택지 2열 판정 = 시각 글리프 근사 — 중앙중 #1·#2·#3 (2026-06-11) ──
    # LaTeX 원문 길이는 근호·분수 명령어가 부풀어 짧은 보기(√30×√6=□√5)를 1열로 강등.
    # 명령어=1글리프 정규화로 화면 폭을 근사 — 긴 전개식(#5)은 여전히 1열(임계 유지).
    from types import SimpleNamespace as _NS
    from core.hwp_com_writer import _choice_complexity as _ccx
    from core.hwp_form_writer import _is_long_choices as _ilc, LONG_CHOICE_LEN as _LCL

    def _ch(n, latex):
        return _NS(number=n, contents=[ContentBlock(type=CT.EQUATION, value=latex)])

    radical = [_ch(i + 1, v) for i, v in enumerate([
        r"\sqrt{27}=\square\sqrt{3}", r"\frac{\sqrt{15}}{\sqrt{3}}=\sqrt{\square}",
        r"\sqrt{30}\times\sqrt{6}=\square\sqrt{5}",
        r"\frac{\sqrt{3}}{\sqrt{2}}=\frac{\sqrt{\square}}{2}",
        r"\sqrt{\frac{8}{7}}\times\sqrt{63}=6\sqrt{\square}"])]
    chk(all(_ccx(c) < _LCL for c in radical[:4]),
        f"R5 근호 보기 글리프 < {_LCL}: {[_ccx(c) for c in radical[:4]]}")
    chk(not _ilc(_NS(choices=radical)), "R5 근호 보기 → 2열(중앙중 #1)")
    expansion = [_ch(i + 1, v) for i, v in enumerate([
        r"(2x-5y)^2 = 4x^2-20xy+25y^2", r"(-4x-3y)^2 = 16x^2+24xy+9y^2",
        r"(-2x+1)(-2x-1) = 4x^2-2x+1", r"(2x-y)(3x+2y) = 6x^2+xy-2y^2"])]
    chk(_ilc(_NS(choices=expansion)), "R5 긴 전개식 보기 → 1열 유지(중앙중 #5)")

    # ── S: tail 경계 — 박스 머리 앞 그림/노트 run 포함 — 장산중 #24 (2026-06-11) ──
    # 발문→그림(노트)→<보기> 순서에서 그림이 발문에 인라인되고 배점이 노트 뒤로 밀리던 회귀.
    # 박스 머리 바로 앞의 그림자리안내/IMAGE/블록수식 연속 run 은 tail 에 포함돼야 한다.
    from core.hwp_com_writer import _tail_start as _ts
    note = _tb("※ 그림 자리 — 원본에서 이 영역을 캡처해 여기에 붙여넣으세요")
    bogi = _tb("<보기> ㄱ. ")
    s1 = [_tb("발문이다 (단, "), _eq("0<k<9"), _tb("인 수)"), note, bogi, _eq("a")]
    chk(_ts(s1) == 3, f"S 박스 앞 노트 tail 포함: {_ts(s1)} (기대 3)")
    img = ContentBlock(type=CT.IMAGE, value="x.png")
    s2 = [_tb("발문이다."), img, bogi, _eq("a")]
    chk(_ts(s2) == 1, f"S 박스 앞 IMAGE tail 포함: {_ts(s2)} (기대 1)")
    # 문장 중간 노트(뒤에 발문 TEXT 계속)는 발문에 남고 tail 은 박스부터(기존 동작 보존).
    s3 = [_tb("발문 앞"), note, _tb("발문 계속이다."), bogi, _eq("a")]
    chk(_ts(s3) == 3, f"S 문장중간 노트 비포함: {_ts(s3)} (기대 3)")
    # 박스 없는 끝 노트(2순위 경로) 기존 동작 유지.
    s4 = [_tb("발문이다."), note]
    chk(_ts(s4) == 1, f"S 끝 노트(2순위): {_ts(s4)} (기대 1)")

    # ── T: 밑줄 실선검정·줄기잎 1:3 저장후 XML 후처리 — 강동중 중1 #1·#6·#20 (2026-06-11) ──
    # underline_run 토글이 폼 기본 밑줄(회색 점선 DOT/#808080)을 상속 → 강조어가 흐린 점선.
    # TableCreate 가 col_widths=[1,3] 을 균등 재배분 → 줄기:잎 1:1. 둘 다 저장후 XML 로 강제.
    from core.hwp_com_writer import _solidify_underline, _fix_stemleaf_colwidth
    # T-1: 밑줄 charPr 회색점선 → 실선검정(type 보존)
    hdr_xml = ('<hh:head><hh:charProperties>'
               '<hh:charPr id="28"><hh:underline type="BOTTOM" shape="DOT" color="#808080"/>'
               '</hh:charPr></hh:charProperties></hh:head>')
    fd3, tmp3 = tempfile.mkstemp(suffix=".hwpx"); os.close(fd3)
    try:
        with zipfile.ZipFile(tmp3, "w") as z:
            z.writestr("Contents/header.xml", hdr_xml)
        n = _solidify_underline(tmp3)
        with zipfile.ZipFile(tmp3) as z:
            g = z.read("Contents/header.xml").decode("utf-8")
        ul = _re.search(r"<hh:underline\b[^>]*/>", g).group(0)
        chk(n == 1 and 'shape="SOLID"' in ul and 'color="#000000"' in ul
            and 'type="BOTTOM"' in ul, f"T-1 밑줄 실선검정: {ul!r} (n={n})")
    finally:
        os.remove(tmp3)

    # T-2: 줄기-잎 표만 1:3(총폭 보존), 비-줄기잎 2열표(z-표)는 미변경
    def _tc(col, w, txt):
        return (f'<hp:tc><hp:cellAddr colAddr="{col}" rowAddr="0"/>'
                f'<hp:cellSz width="{w}" height="282"/><hp:subList><hp:p><hp:run>'
                f'<hp:t>{txt}</hp:t></hp:run></hp:p></hp:subList></hp:tc>')
    stbl = ('<hp:tbl colCnt="2" rowCnt="6">'
            '<hp:sz width="29056" widthRelTo="ABSOLUTE" height="8417" heightRelTo="ABSOLUTE" protect="0"/>'
            + _tc("0", 14528, "줄기") + _tc("1", 14528, "잎")
            + "".join(_tc("0", 14528, str(r)) + _tc("1", 14528, "6 8") for r in range(1, 6))
            + '</hp:tbl>')
    ztbl = ('<hp:tbl colCnt="2" rowCnt="2">'
            '<hp:sz width="29056" widthRelTo="ABSOLUTE" height="2000" heightRelTo="ABSOLUTE" protect="0"/>'
            + _tc("0", 14528, "z") + _tc("1", 14528, "P(0≤Z≤z)")
            + _tc("0", 14528, "0.0") + _tc("1", 14528, "0.5000")
            + '</hp:tbl>')
    sec_t = "<hp:sec>" + stbl + ztbl + "</hp:sec>"
    fd4, tmp4 = tempfile.mkstemp(suffix=".hwpx"); os.close(fd4)
    try:
        with zipfile.ZipFile(tmp4, "w") as z:
            z.writestr("Contents/section0.xml", sec_t)
        nt = _fix_stemleaf_colwidth(tmp4)
        with zipfile.ZipFile(tmp4) as z:
            g = z.read("Contents/section0.xml").decode("utf-8")
        st = _re.search(r"<hp:tbl\b.*?줄기.*?</hp:tbl>", g, _re.S).group(0)
        sw = [w for _, w in _re.findall(r'colAddr="(\d)"[^/]*/><hp:cellSz width="(\d+)"', st)]
        zt = _re.search(r"<hp:tbl\b(?:(?!</hp:tbl>).)*?P\(0.*?</hp:tbl>", g, _re.S).group(0)
        zw = [w for _, w in _re.findall(r'colAddr="(\d)"[^/]*/><hp:cellSz width="(\d+)"', zt)]
        chk(nt == 1 and set(sw[0::2]) == {"7264"} and set(sw[1::2]) == {"21792"},
            f"T-2 줄기잎 1:3: {sw[:2]} (nt={nt})")
        chk(set(zw) == {"14528"}, f"T-2 z-표 미변경: {zw[:2]}")
    finally:
        os.remove(tmp4)

    # ── U: 발문 기하 문맥 → 선택지 점 좌표 로만+이탤릭 — 대륜중 중1 #1 (2026-06-11) ──
    # "좌표평면 위의 점 A,B,C,D,E…" 선택지 A(2,3) 은 선택지 자체엔 기하 키워드가 없어 점 이름이
    # 이탤릭으로 새던 것 → 발문 기하 문맥을 선택지로 전파해 \mathrm{A}\mathit{(2,3)} 로 로만+이탤릭.
    from core.content_parser import parse_ocr_response as _por, build_document as _bd
    from core.latex_to_hwpeq import latex_to_hwpeq as _lh
    def _choice_eq(stem, cval):
        ocr = {"questions": [{"number": 1, "score": 3,
               "contents": [{"type": "text", "value": stem}],
               "choices": [{"number": 1, "contents": [{"type": "equation", "value": cval}]}]}]}
        q = _bd([_por(ocr, page_number=1)]).pages[0].questions[0]
        return q.choices[0].contents[0].value
    geo = _choice_eq("좌표평면 위의 점 A, B, C, D, E의 좌표를 나타낸 것은?", "B(-3, 1)")
    chk(geo == r"\mathrm{B}\mathit{(-3, 1)}", f"U 점좌표 선택지 로만+이탤릭: {geo!r}")
    chk(_lh(geo, italicize_stat=False) == "rm B it {(-3,~1)}", f"U hwp 변환: {_lh(geo, italicize_stat=False)!r}")
    nongeo = _choice_eq("확률변수 X에 대하여 옳은 것은?", "P(X=2)")   # 비기하 발문 → 로만화 안 함
    chk(nongeo == "P(X=2)", f"U 확통 무회귀(이탤릭 유지): {nongeo!r}")

    # ── U2: <조건> 박스 ○ 항목 줄바꿈 — 대륜중 중1 #15 (2026-06-11) ──
    # ○(U+25CB)를 _BOX_BREAK_RE 경계로 추가(but _BULLET_RE 제외=표시) → 각 ○ 가 자기 줄에서 시작.
    class _Rec:
        def __init__(s): s.log = []
        def text(s, t): s.log.append(("T", t))
        def break_para(s): s.log.append(("BR",))
        def equation(s, e): s.log.append(("EQ",))
        def __getattr__(s, n): return lambda *a, **k: None
    wbox = W.HwpComWriter.__new__(W.HwpComWriter); wbox.s = _Rec()
    wbox._write_box_content([_tb("<조건> ○ 첫째 조건이다. ○ 둘째 조건이다. ○ 셋째 조건이다.")])
    log = wbox.s.log
    # ○(논리 불릿)은 작은 •(표시 글리프)로 치환돼 출력된다(사용자 2026-06-11).
    circles = [i for i, e in enumerate(log) if e == ("T", W._COND_BULLET_DISPLAY + " ")]
    chk(len(circles) == 3, f"U2 조건 불릿 3항목 표시(•): {[e for e in log if e[0]=='T']}")
    chk(not any(e == ("T", "○ ") for e in log), "U2 큰 ○ 글리프 미출력")
    # 각 불릿 앞엔 break_para(라벨 직후 첫 불릿 포함 — <조건> 뒤 BR 후 불릿)
    chk(all(("BR",) in log[max(0, i-1):i] for i in circles), f"U2 각 불릿 앞 줄바꿈: {log}")

    # ── V: 순환소수 dot 표기 — 경명여중 중2 #1 (2026-06-11) ──
    # \dot{} 순환마디는 HWP ``dot {d}`` over-dot 로(양끝 숫자 위 점). 과거 bar(overline)
    # 통일은 잘못된 무공백 문법 오진 — .testkit/dot_test.py 로 dot 렌더 실측 확정.
    v1 = latex_to_hwpeq(r"0.1\dot{5}\dot{7}")
    chk("dot {5}" in v1 and "dot {7}" in v1 and "bar" not in v1, f"V 순환소수 dot: {v1!r}")
    v2 = latex_to_hwpeq(r"0.\dot{3}7\dot{5}")   # 중간 일반숫자 7 보존
    chk(v2 == "0. dot {3}7 dot {5}", f"V 순환마디 중간숫자 보존: {v2!r}")

    # ── W: 괄호형 배점 (N점) 제거 — 경명여중 중2 #20·#21 (2026-06-11) ──
    # score 필드가 있는데 본문 ``(7점)`` 이 안 지워져 우측정렬 ``[7점]`` 과 이중 출력되던 회귀.
    from core.content_parser import _SCORE_TEXT_RE
    chk(_SCORE_TEXT_RE.sub("", "서술하시오. (7점)").strip() == "서술하시오.", "W (7점) 소괄호 제거")
    chk(_SCORE_TEXT_RE.sub("", "구하시오. [10점]").strip() == "구하시오.", "W [10점] 대괄호 무회귀")

    # ── X: 유령 박스 조각 제거 — 경명여중 중2 #20 (2026-06-11) ──
    # 발문 한글 부분문자열을 담은 <상자> 환각 블록을 raw 단계에서 드롭.
    from core.content_parser import _drop_duplicate_box_fragments
    raw = [{"type": "text", "value": "<상자> 자연수의 꼴로 나타낸 후 몇 자리 자연"},
           {"type": "text", "value": "n은 자연수의 꼴로 나타낸 후 몇 자리 자연수인지 구하시오."}]
    kept = _drop_duplicate_box_fragments(raw)
    chk(len(kept) == 1 and "n은" in kept[0]["value"], f"X 유령 박스 드롭: {[b['value'][:12] for b in kept]}")
    # 무회귀: 발문에 없는 진짜 박스는 보존.
    raw2 = [{"type": "text", "value": "다음 보기에서 고르시오."},
            {"type": "text", "value": "<상자> 독립적인 지문 내용 가나다라마바사."}]
    chk(len(_drop_duplicate_box_fragments(raw2)) == 2, "X 진짜 박스 보존")

    # ── Y: 박스 안 •B 줄바꿈 — 경명여중 중2 #11 (2026-06-11) ──
    # ASCII 수식 조각 앞 선행 불릿이 수식에 흡수되지 않고 별도 TEXT 로 분리돼야 박스 줄바꿈.
    from core.content_parser import _split_latex_commands
    yb = _split_latex_commands(r"A = 6x^4 • B = (-x^2)^3")
    has_bullet_text = any(b.type.name == "TEXT" and "•" in b.value for b in yb)
    chk(has_bullet_text, f"Y 불릿 별도 TEXT: {[(b.type.name, b.value) for b in yb]}")

    # ── T2: post 가 또 다른 박스(<조건>)면 박스로 — 새론중 #16 (2026-06-11) ──
    # <보기> 박스 뒤 <조건> 박스가 박스 그룹화에서 발문 연속(post)으로 오분류돼 평문 렌더되던
    # 회귀. _post_is_box 로 박스 머리를 감지해 ① 배점 안 미룸(발문 끝) ② post 를 박스로 렌더.
    from core.hwp_com_writer import _post_is_box
    cond_post = [_tb("<조건> ○ 단답형으로 답만 적을 것.")]
    bogi_post = [_tb("<보기> ㄱ. "), _eq("a")]
    sangja_post = [_tb("<상자> 모든 자연수 "), _eq("n")]
    real_post = [_tb("이때 "), _eq("P(Y)"), _tb("의 값을 구하시오.")]  # 장산중 #5 류 진짜 발문연속
    chk(_post_is_box(cond_post), "T2 <조건> post = 박스")
    chk(_post_is_box(bogi_post), "T2 <보기> post = 박스")
    chk(_post_is_box(sangja_post), "T2 <상자> post = 박스")
    chk(not _post_is_box(real_post), "T2 발문연속(이때 …)은 박스 아님")
    chk(not _post_is_box([]), "T2 빈 post = 박스 아님")

    if fails:
        print("FAIL test_render_fixes:")
        print("\n".join(fails))
        return 1
    print("OK test_render_fixes (cell/value-box/caption/shading/essay-label/overline/relabel/"
          "bigstar/boxed/labelless/solo/mixed-label/rm-space/cond-header/form-underline/"
          "sqrt-space/choice-glyph/tail-note/underline-solid/stemleaf-13/choice-geo/cond-circle/"
          "repeat-dot/paren-score/phantom-box/box-bullet/post-box)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
