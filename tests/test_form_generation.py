# 폼 세대(25년 7종 ↔ 26년 개정 9종) 차이 흡수 회귀 (stdlib only, HWP COM·API·키 0).
#   python tests/test_form_generation.py
#
# 2026-10-06 대수회 폼을 26년 개정 9종으로 교체하면서 writer 가 "폼 구조를 상수로 박아 둔"
# 지점이 한꺼번에 드러났다. 전부 **문서에서 읽는다**로 고쳤고, 그 판독 로직을 여기서 잠근다.
#   A. 정답·해설 글자모양 ID — 개정 폼은 한 칸 당겨져(21→20) 상수 21 이면 12pt 볼드로 나간다
#   B. 머리말/꼬리말 자리표시 — "OO고"·"O학기"·"OO고사"·"공통수학O"·('년' 빠진 꼬리말)
#      + 치환은 머리말·꼬리말·글상자 **안에서만**(본문 변조 금지)
#   C. 시험범위 자리표시 — "시작 범위 ~ 끝 범위"(구 폼은 " ~ ")
#   D. 메타란 run 교체가 단락 경계를 넘던 잠복 버그 + 표 셀·미주에 든 토큰(가장 안쪽만)
#   E. 소문항 마커 글리프(⑴~⒇) / OCR 이 준 ⑴ 접두 제거 / 정답면 생성 머리도 같은 양식
# B·D·A 의 일부와 E 의 정답면 머리는 Codex 리뷰(2026-10-06)에서 나온 입력이다.
import os
import re
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from core.hwp_form_writer import (  # noqa: E402
    _META_TOKEN_NA, _META_TOKEN_SO, _RANGE_PH_RE, _answer_charpr, _fill_exam_range,
    _fill_form_header, _header_regions, _inject_answer_runs, _inject_essay_meta,
    _inject_solutions, _merged_answer, _merged_solution, _strip_leading_submarker,
    _sub_marker)
from models.exam_document import ContentBlock, ContentType, Question  # noqa: E402

FAILS: list[str] = []


def chk(cond, msg):
    if not cond:
        FAILS.append(msg)


def _tb(v):
    return ContentBlock(type=ContentType.TEXT, value=v)


def _eq(v):
    return ContentBlock(type=ContentType.EQUATION, value=v)


def _hwpx(section: str, header: str | None = None) -> str:
    fd, fp = tempfile.mkstemp(suffix=".hwpx")
    os.close(fd)
    with zipfile.ZipFile(fp, "w") as z:
        z.writestr("Contents/section0.xml", section)
        if header is not None:
            z.writestr("Contents/header.xml", header)
    return fp


def _sec_of(fp: str) -> str:
    with zipfile.ZipFile(fp) as z:
        return z.read("Contents/section0.xml").decode("utf-8")


LS = '<hp:linesegarray><hp:lineseg textpos="0"/></hp:linesegarray>'


def _note(n: int, num_cp: str, text_cp: str | None) -> str:
    """미주 1개 — [자동번호 run(num_cp)] + [내용 run(text_cp)]. 폼 실측 구조 그대로.
    ``text_cp=None`` 이면 번호 run 만 있는 미주."""
    body = (f'<hp:run charPrIDRef="{text_cp}"><hp:t> </hp:t></hp:run>'
            if text_cp is not None else "")
    return (f'<hp:endNote number="{n}"><hp:subList><hp:p id="0" paraPrIDRef="11">'
            f'<hp:run charPrIDRef="{num_cp}"><hp:ctrl><hp:autoNum num="{n}"/></hp:ctrl></hp:run>'
            f'{body}{LS}</hp:p></hp:subList></hp:endNote>')


def test_answer_charpr():
    new = "<hs:sec>" + "".join(_note(i, "21", "20") for i in (1, 2, 3)) + "</hs:sec>"
    old = "<hs:sec>" + "".join(_note(i, "22", "21") for i in (1, 2, 3)) + "</hs:sec>"
    chk(_answer_charpr(new) == "20", f"A 개정 폼 내용 charPr=20: {_answer_charpr(new)!r}")
    chk(_answer_charpr(old) == "21", f"A 25년 폼 내용 charPr=21: {_answer_charpr(old)!r}")
    chk(_answer_charpr("<hs:sec></hs:sec>") == "21", "A 미주도 선택지도 없음 → 폴백 21")
    # 폼 자체의 흔들림(중3 개정 폼은 뒤쪽 미주 번호 run 이 다른 charPr) — 내용 run 최빈값.
    mixed = "<hs:sec>" + _note(1, "21", "20") + _note(2, "21", "20") + _note(3, "23", "20") + "</hs:sec>"
    chk(_answer_charpr(mixed) == "20", "A 번호 run 이 섞여도 내용 run 기준")
    # (Codex) 번호 run 만 있는 미주 한 개뿐 — 상수 21(개정 폼에선 12pt 볼드)로 떨어지면 안 된다.
    # 선택지 줄 머리(①)의 글자모양으로 복구한다.
    choice = ('<hp:p id="0" paraPrIDRef="25"><hp:run charPrIDRef="20"><hp:t>① </hp:t></hp:run>'
              + LS + '</hp:p>')
    lone = "<hs:sec>" + _note(1, "21", None) + choice + "</hs:sec>"
    chk(_answer_charpr(lone) == "20", f"A 내용 run 없는 미주 → ① 글자모양: {_answer_charpr(lone)!r}")
    # (Codex) 번호 단락에 뒤 run 이 없고 **다음 단락**에 run 이 둘(20, 22) 연속 — 단락을
    # 건너가 둘째(22)를 내용 ID 로 집으면 안 된다.
    cross = ('<hs:sec><hp:endNote number="1"><hp:subList>'
             '<hp:p id="0" paraPrIDRef="11"><hp:run charPrIDRef="21"><hp:ctrl>'
             '<hp:autoNum num="1"/></hp:ctrl></hp:run>' + LS + '</hp:p>'
             '<hp:p id="0" paraPrIDRef="11"><hp:run charPrIDRef="20"><hp:t>가</hp:t></hp:run>'
             '<hp:run charPrIDRef="22"><hp:t>나</hp:t></hp:run>' + LS + '</hp:p>'
             '</hp:subList></hp:endNote>' + choice + '</hs:sec>')
    chk(_answer_charpr(cross) == "20", f"A 단락 건너 오인 금지: {_answer_charpr(cross)!r}")

    # 주입된 정답·해설 run 이 **미주 번호 글자모양(12pt 볼드)** 을 쓰지 않는다.
    hdr = ('<hh:charPr id="20" height="1100" textColor="#000000"/>'
           '<hh:charPr id="21" height="1200" textColor="#000000"><hh:bold/></hh:charPr>')
    fp = _hwpx(new, hdr)
    try:
        n = _inject_answer_runs(fp, [[[_tb("④")]], [[_tb("x="), _eq("50")]], []])
        ns = _inject_solutions(fp, [[], [[_tb("step1) 세운다.")], [_eq("2x=100")]], []])
        got = _sec_of(fp)
    finally:
        os.remove(fp)
    chk(n == 2 and ns == 2, f"A 주입 건수: 정답 {n} 해설 {ns}")
    chk('<hp:run charPrIDRef="20"><hp:t>④</hp:t></hp:run>' in got, "A 정답 텍스트 run = 20")
    chk('<hp:run charPrIDRef="21"><hp:t>' not in got and
        '<hp:run charPrIDRef="21"><hp:equation' not in got,
        "A 정답·해설에 번호 글자모양(21) 미사용")
    chk('baseUnit="1100"' in got and 'baseUnit="1200"' not in got,
        "A 수식 baseUnit = 내용 charPr 높이(1100) — 번호 높이(1200) 아님")


def _head(*texts) -> str:
    """머리말 표 칸들."""
    return "<hp:header>" + "".join(f"<hp:t>{t}</hp:t>" for t in texts) + "</hp:header>"


def _foot(*texts) -> str:
    return "<hp:footer>" + "".join(f"<hp:t>{t}</hp:t>" for t in texts) + "</hp:footer>"


def _banner(*texts) -> str:
    """첫 쪽 배너 — 글상자 안에 묶음 개체, 그 안에 칸별 글상자(중첩)."""
    return ("<hp:rect><hp:drawText><hp:container>"
            + "".join(f"<hp:rect><hp:drawText><hp:t>{t}</hp:t></hp:drawText></hp:rect>"
                      for t in texts)
            + "</hp:container></hp:drawText></hp:rect>")


def test_header_placeholders():
    def run(body, values):
        fp = _hwpx("<hs:sec>" + body + "</hs:sec>")
        try:
            n = _fill_form_header(fp, values)
            return n, _sec_of(fp)
        finally:
            os.remove(fp)

    mid = {"학교": "침산중", "학년": "중2", "과목": "수학", "년도": "2026", "학기": "2",
           "구분": "중간"}
    n, got = run(_head("2025년 O학기 OO고사", "OO중 2학년 수학", "여기에 학원 로고 또는 이름")
                 + _foot("OO중 27년 O학기 OO고사 대비 (수학)")
                 + _banner("2025년 O학기 OO고사", "OO중 2학년 수학"), mid)
    chk(got.count("<hp:t>2026년 2학기 중간고사</hp:t>") == 2, f"B 시험명(머리말+배너): {got}")
    chk(got.count("<hp:t>침산중 2학년 수학</hp:t>") == 2, f"B 가운데(자리표시 OO 까지): {got}")
    chk("<hp:t>침산중 26학년 2학기 중간고사 대비 (수학)</hp:t>" in got, f"B 꼬리말: {got}")
    chk("OO" not in got and "O학기" not in got, f"B 자리표시 O 잔존 0: {got}")
    chk("여기에 학원 로고 또는 이름" in got, "B 학원 로고 칸은 사람이 채운다(보존)")

    # ⭐ (Codex) 치환은 머리말·꼬리말·글상자 **안에서만** — 문항 본문은 건드리지 않는다.
    body_q = ('<hp:p><hp:run><hp:t>고1학년 수학 성적의 평균을 구하시오.</hp:t></hp:run></hp:p>'
              '<hp:p><hp:run><hp:t>2024년 학기 고사 결과이다.</hp:t></hp:run></hp:p>'
              '<hp:tbl><hp:t> ~ </hp:t></hp:tbl>')
    n, got = run(_head("OO중 2학년 수학") + body_q, dict(mid, 범위="일차함수 ~ 연립방정식"))
    chk("<hp:t>고1학년 수학 성적의 평균을 구하시오.</hp:t>" in got, f"B 본문 '고1학년 수학' 보존: {got}")
    chk("<hp:t>2024년 학기 고사 결과이다.</hp:t>" in got, "B 본문 '…년 학기 고사' 보존")
    chk("<hp:tbl><hp:t> ~ </hp:t></hp:tbl>" in got, "B 본문 표 셀의 평문 ' ~ ' 는 시험범위가 아니다")
    chk("<hp:header><hp:t>침산중 2학년 수학</hp:t></hp:header>" in got, "B 머리말은 치환")
    # 구간 판독 — 중첩 글상자는 바깥 하나로.
    sec = "<hs:sec>" + _banner("a", "b") + "<hp:p/>" + _foot("c") + "</hs:sec>"
    spans = _header_regions(sec)
    chk(len(spans) == 2 and sec[spans[0][0]:spans[0][1]].startswith("<hp:drawText>")
        and sec[spans[0][0]:spans[0][1]].count("<hp:drawText>") == 3,
        f"B 중첩 글상자 = 바깥 구간 하나: {spans}")

    # 고1 폼 — "공통수학O" 를 한 덩어리로(안 그러면 '공통' 이 남는다). 표시명 공수2→공통수학2.
    hi1 = {"학교": "대진고", "학년": "고1", "과목": "공수2", "년도": "2025", "학기": "2",
           "구분": "기말"}
    n, got = run(_banner("OO고 2학년 공통수학O") + _foot("OO고 25년 O학기 OO고사 대비 (공통수학O)"),
                 hi1)
    chk("<hp:t>대진고 1학년 공통수학2</hp:t>" in got, f"B 고1 가운데: {got}")
    chk("<hp:t>대진고 25학년 2학기 기말고사 대비 (공통수학2)</hp:t>" in got, f"B 고1 꼬리말: {got}")
    chk("공통공통" not in got and "수학O" not in got, f"B '공통'·O 잔존 0: {got}")

    # 대수 폼 꼬리말은 '년' 이 빠져 있다("27 O학기") — 그래도 통째 치환.
    alg = {"학교": "강동고", "학년": "고2", "과목": "수1", "년도": "2025", "학기": "1",
           "구분": "기말"}
    n, got = run(_foot("OO고 27 O학기 OO고사 대비 (대수)") + _head("OO고 2학년 대수"), alg)
    chk("<hp:t>강동고 25학년 1학기 기말고사 대비 (수학1)</hp:t>" in got, f"B '년' 없는 꼬리말: {got}")
    chk("<hp:t>강동고 2학년 수학1</hp:t>" in got, f"B 대수 폼 가운데: {got}")

    # 확통 폼(학년 토큰 없는 과목 폼)을 고3 이 쓴다 — 학년은 값이 덮어쓴다.
    st3 = {"학교": "대진고", "학년": "고3", "과목": "확통", "년도": "2025", "학기": "1",
           "구분": "기말"}
    n, got = run(_head("OO고 2학년 확률과 통계")
                 + _foot("OO고 27년 O학기 OO고사 대비 (확률과 통계)"), st3)
    chk("<hp:t>대진고 3학년 확률과 통계</hp:t>" in got, f"B 고3 확통: {got}")

    # 25년 폼 자리표시(빈칸형)도 그대로 통한다 + 꼬리말 "(정답)" 보존.
    n, got = run(_head("2024년 학기 고사", "고 1학년 수학")
                 + _foot("중 25년 학기 고사 대비 (수학) (정답)"), mid)
    chk("<hp:t>2026년 2학기 중간고사</hp:t>" in got and "<hp:t>침산중 2학년 수학</hp:t>" in got,
        f"B 구 폼 무회귀: {got}")
    chk("대비 (수학) (정답)</hp:t>" in got, f"B 구 폼 (정답) 보존: {got}")

    # 미적분 번호는 과목명이다(과거 '미적분1'→'미적분' 강등 폐기).
    n, got = run(_head("OO고 2학년 미적분1"), dict(alg, 과목="미적1"))
    chk("<hp:t>강동고 2학년 미적분1</hp:t>" in got, f"B 미적1 → 미적분1: {got}")


def test_range_placeholder():
    chk(_RANGE_PH_RE.search("<hp:t>시작 범위 ~ 끝 범위</hp:t>") is not None, "C 개정 자리표시 매칭")
    chk(_RANGE_PH_RE.search("<hp:t> ~ </hp:t>") is not None, "C 구 자리표시 매칭")
    chk(_RANGE_PH_RE.search("<hp:t>1 ~ 5</hp:t>") is None, "C 본문 범위표기는 미매칭")
    chk(_RANGE_PH_RE.search("<hp:t>시작 범위 ~ 끝 범위입니다</hp:t>") is None,
        "C 런 전체가 자리표시일 때만")
    for ph in ("시작 범위 ~ 끝 범위", " ~ "):
        fp = _hwpx("<hs:sec><hp:tbl><hp:t> ~ </hp:t></hp:tbl>"
                   f"<hp:drawText><hp:run charPrIDRef=\"18\"><hp:t>{ph}</hp:t></hp:run></hp:drawText>"
                   "<hp:t>문항 1~5 는</hp:t></hs:sec>")
        try:
            n = _fill_exam_range(fp, "삼각비 ~ 대푯값과 산포도")
            got = _sec_of(fp)
        finally:
            os.remove(fp)
        chk(n == 1 and "<hp:t>삼각비 ~ 대푯값과 산포도</hp:t>" in got and "시작 범위" not in got,
            f"C 범위 치환({ph!r}): n={n} {got}")
        chk("<hp:t>문항 1~5 는</hp:t>" in got, "C 본문 물결 보존")
        # 배너보다 **앞**에 있는 본문 표 셀의 평문 ' ~ ' 를 먼저 집으면 안 된다.
        chk(got.startswith("<hs:sec><hp:tbl><hp:t> ~ </hp:t></hp:tbl>"),
            f"C 글상자 밖 ' ~ ' 보존({ph!r}): {got}")
    # 배너가 없으면(자리표시 없음) 아무것도 안 한다.
    fp = _hwpx("<hs:sec><hp:tbl><hp:t> ~ </hp:t></hp:tbl></hs:sec>")
    try:
        chk(_fill_exam_range(fp, "가 ~ 나") == 0, "C 글상자 밖만 있으면 no-op")
    finally:
        os.remove(fp)
    # 머리말 채움(scope.txt 경로)도 같은 자리표시를 쓴다.
    fp = _hwpx("<hs:sec>" + _banner("시작 범위 ~ 끝 범위", "OO중 1학년 수학") + "</hs:sec>")
    try:
        _fill_form_header(fp, {"학교": "A중", "학년": "중1", "과목": "수학", "년도": "2025",
                               "학기": "1", "구분": "기말", "범위": "정수와 유리수 ~ 일차방정식"})
        got = _sec_of(fp)
    finally:
        os.remove(fp)
    chk("<hp:t>정수와 유리수 ~ 일차방정식</hp:t>" in got, f"C header_values['범위']: {got}")


def _para(pp, inner):
    return f'<hp:p id="0" paraPrIDRef="{pp}" styleIDRef="0">{inner}{LS}</hp:p>'


def _meta(label, color):
    return _para("11", f'<hp:run charPrIDRef="22"><hp:t><hp:markpenBegin color="{color}"/>'
                       f' [{label}]  <hp:markpenEnd/></hp:t></hp:run>')


def _tok(tok):
    return _para("11", f'<hp:run charPrIDRef="20"><hp:t>{tok}</hp:t></hp:run>')


def _balanced(xml: str) -> bool:
    """여는 태그(자기닫힘 제외) 수 == 닫는 태그 수 — 단락·run·표·미주 전부."""
    return all(len(re.findall(r"<hp:%s\b[^>]*(?<!/)>" % t, xml)) == xml.count("</hp:%s>" % t)
               for t in ("p", "run", "tbl", "tc", "endNote", "subList"))


def test_essay_meta_paragraph_boundary():
    blank26 = _para("26", '<hp:run charPrIDRef="20"/>')
    blank11 = _para("11", '<hp:run charPrIDRef="20"/>')
    sub = _para("26", '<hp:run charPrIDRef="20"><hp:t> 소문항 본문</hp:t></hp:run>')
    templates = _meta("중단원", "#FF843A") + _meta("난이도", "#42C7F1")
    # 객관식 슬롯(살아있는 메타란 = 템플릿) + 빈 줄 + 서술형 소문항 + 답란 빈 줄 + 토큰 2줄 + 빈 줄
    sec = ("<hs:sec>" + templates + blank11 + sub + blank26 + _tok(_META_TOKEN_SO)
           + _tok(_META_TOKEN_NA) + blank11 + "</hs:sec>")
    fp = _hwpx(sec)
    try:
        n = _inject_essay_meta(fp)
        got = _sec_of(fp)
    finally:
        os.remove(fp)
    chk(_META_TOKEN_SO not in got and _META_TOKEN_NA not in got, "D 토큰 0")
    chk(got.count("[중단원]") == 2 and got.count("[난이도]") == 2, f"D 메타란 2쌍: {got}")
    chk(_balanced(got), "D 태그 균형")
    # ⭐ 주입된 [중단원] 단락은 **토큰 단락의 문단모양(11)** — 앞 빈 단락(26)의 것이 아니다.
    pps = re.findall(r'<hp:p id="0" paraPrIDRef="(\d+)"[^>]*>(?:(?!</hp:p>).)*?\[중단원\]', got, re.S)
    chk(pps == ["11", "11"], f"D [중단원] 단락 paraPr: {pps}")
    # 토큰 바로 앞 빈 줄(답란 잔여)은 버린다 — 종전(우연한) 레이아웃을 명시적으로 유지.
    chk(got.count('paraPrIDRef="26"') == 1, f"D 토큰 앞 빈 단락 제거(소문항 줄만 26): {got}")
    # 토큰과 떨어진 빈 줄은 그대로.
    chk(got.count('<hp:run charPrIDRef="20"/>') == 2, "D 다른 빈 줄은 보존")
    chk(n >= 2, f"D 교체 건수: {n}")

    # (Codex) 토큰이 **표 첫 셀 첫 단락**에 있다 — 표를 품은 바깥 run 에서 매치를 시작하면
    # 표·셀·단락 여는 태그를 삼켜 XML 이 깨진다. 토큰이 든 가장 안쪽 run 만 바꾼다.
    cell = ('<hp:tc><hp:subList>' + _tok(_META_TOKEN_SO) + '</hp:subList></hp:tc>')
    in_tbl = _para("11", '<hp:run charPrIDRef="20"><hp:tbl id="1"><hp:tr>' + cell
                         + '</hp:tr></hp:tbl><hp:t/></hp:run>')
    fp = _hwpx("<hs:sec>" + templates + in_tbl + _tok(_META_TOKEN_NA) + "</hs:sec>")
    try:
        _inject_essay_meta(fp)
        got = _sec_of(fp)
    finally:
        os.remove(fp)
    chk(_balanced(got), f"D 표 셀 토큰 — 태그 균형: {got}")
    chk("<hp:tbl id=\"1\">" in got and _META_TOKEN_SO not in got and got.count("[중단원]") == 2,
        f"D 표 셀 토큰 — 표 보존 + 안쪽 run 교체: {got}")

    # (Codex) 폼에 메타 템플릿이 **없고** 토큰이 미주 첫 단락에 있다 — 토큰 단락 제거가 미주를
    # 품은 바깥 본문 단락에서 시작하면 미주·단락 닫는 태그만 남는다. 가장 안쪽 단락만 지운다.
    note = ('<hp:endNote number="1"><hp:subList>' + _tok(_META_TOKEN_SO)
            + _para("11", '<hp:run charPrIDRef="20"><hp:t>남는 줄</hp:t></hp:run>')
            + '</hp:subList></hp:endNote>')
    outer = _para("11", '<hp:run charPrIDRef="21"><hp:ctrl>' + note + '</hp:ctrl></hp:run>'
                        '<hp:run charPrIDRef="20"><hp:t>본문</hp:t></hp:run>')
    fp = _hwpx("<hs:sec>" + outer + "</hs:sec>")          # 템플릿 없음
    try:
        _inject_essay_meta(fp)
        got = _sec_of(fp)
    finally:
        os.remove(fp)
    chk(_balanced(got), f"D 템플릿 없음 + 미주 안 토큰 — 태그 균형: {got}")
    chk(_META_TOKEN_SO not in got and "남는 줄" in got and "본문" in got
        and "<hp:endNote" in got, f"D 미주·바깥 본문 보존, 토큰 단락만 제거: {got}")


def test_sub_marker():
    chk(_sub_marker(1, True) == "⑴" and _sub_marker(3, True) == "⑶", "E 글리프 ⑴⑶")
    chk(_sub_marker(20, True) == "⒇", "E 글리프 상한 ⒇")
    chk(_sub_marker(21, True) == "(21)", "E 21번째부터는 글리프가 없다 → (k)")
    chk(_sub_marker(2, False) == "(2)", "E 25년 폼 = (k)")
    # OCR 이 소문항 본문 머리에 ⑴ 를 남기면 우리 마커와 겹친다 → 제거.
    out = _strip_leading_submarker([_tb("⑴ 넓이를 구하시오.")])
    chk((out[0].value or "").startswith("넓이"), f"E ⑴ 접두 제거: {out[0].value!r}")

    # 정답면에 **우리가 붙이는** 소문항 머리 — 폼이 ⑴ 양식이면 ⑴ 수식 객체(본문 마커와 동일).
    def subq(ans, sol):
        s = Question(number=1, contents=[])
        s.answer, s.solution = ans, sol
        return s

    q = Question(number=20, contents=[])
    q.sub_questions = [subq([[_tb("넓이 4")]], [[_tb("s1")]]), subq([[_eq("x=3")]], [[_tb("s2")]])]
    shape = lambda lines: [[(b.type.name, b.value) for b in ln] for ln in lines]  # noqa: E731
    chk(shape(_merged_answer(q, True)) == [[("EQUATION", "⑴"), ("TEXT", " 넓이 4")],
                                           [("EQUATION", "⑵"), ("EQUATION", "x=3")]],
        f"E 정답 머리(⑴ 양식): {shape(_merged_answer(q, True))}")
    chk(shape(_merged_solution(q, True)) == [[("EQUATION", "⑴")], [("TEXT", "s1")],
                                             [("EQUATION", "⑵")], [("TEXT", "s2")]],
        f"E 해설 머리(⑴ 양식): {shape(_merged_solution(q, True))}")
    # 25년 폼(기본값)은 종전 그대로 — 평문 "(k) ".
    chk(shape(_merged_answer(q)) == [[("TEXT", "(1) "), ("TEXT", "넓이 4")],
                                     [("TEXT", "(2) "), ("EQUATION", "x=3")]],
        f"E 정답 머리(25년 폼 무회귀): {shape(_merged_answer(q))}")
    chk(shape(_merged_solution(q)) == [[("TEXT", "(1)")], [("TEXT", "s1")],
                                       [("TEXT", "(2)")], [("TEXT", "s2")]],
        "E 해설 머리(25년 폼 무회귀)")
    # 부모에 답·해설이 있으면 머리를 만들지 않는다(원문 표기 그대로 — 건드리지 않는다).
    q.answer, q.solution = [[_tb("(1) 원문 그대로")]], [[_tb("(1) 원문 해설")]]
    chk(shape(_merged_answer(q, True)) == [[("TEXT", "(1) 원문 그대로")]]
        and shape(_merged_solution(q, True)) == [[("TEXT", "(1) 원문 해설")]],
        "E 부모 답·해설은 양식과 무관하게 원문 그대로")
    # 원본 블록을 훼손하지 않는다(머리 뒤 공백은 사본에).
    q2 = Question(number=21, contents=[])
    blk = _tb("넓이 4")
    q2.sub_questions = [subq([[blk]], [])]
    _merged_answer(q2, True)
    chk(blk.value == "넓이 4", "E 원본 블록 불변")


def run():
    for t in (test_answer_charpr, test_header_placeholders, test_range_placeholder,
              test_essay_meta_paragraph_boundary, test_sub_marker):
        t()
    if FAILS:
        print("FAIL:")
        for f in FAILS:
            print(" -", f)
        return 1
    print("OK test_form_generation (answer-charpr / header-placeholder+region / range / "
          "meta-para-boundary+nested / sub-marker+answer-head)")
    return 0


if __name__ == "__main__":
    sys.exit(run())
