# 폼 세대(25년 7종 ↔ 26년 개정 9종) 차이 흡수 회귀 (stdlib only, HWP COM·API·키 0).
#   python tests/test_form_generation.py
#
# 2026-10-06 대수회 폼을 26년 개정 9종으로 교체하면서 writer 가 "폼 구조를 상수로 박아 둔"
# 지점이 한꺼번에 드러났다. 전부 **문서에서 읽는다**로 고쳤고, 그 판독 로직을 여기서 잠근다.
#   A. 정답·해설 글자모양 ID — 개정 폼은 한 칸 당겨져(21→20) 상수 21 이면 12pt 볼드로 나간다
#   B. 머리말/꼬리말 자리표시 — "OO고"·"O학기"·"OO고사"·"공통수학O"·('년' 빠진 꼬리말)
#   C. 시험범위 자리표시 — "시작 범위 ~ 끝 범위"(구 폼은 " ~ ")
#   D. 메타란 run 교체가 단락 경계를 넘던 잠복 버그(빈 단락의 문단모양을 물려받음)
#   E. 소문항 마커 글리프(⑴~⒇) / OCR 이 준 ⑴ 접두 제거
import os
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from core.hwp_form_writer import (  # noqa: E402
    _META_TOKEN_NA, _META_TOKEN_SO, _RANGE_PH_RE, _answer_charpr, _fill_exam_range,
    _fill_form_header, _inject_answer_runs, _inject_essay_meta, _inject_solutions,
    _strip_leading_submarker, _sub_marker)
from models.exam_document import ContentBlock, ContentType  # noqa: E402

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


def _note(n: int, num_cp: str, text_cp: str) -> str:
    """미주 1개 — [자동번호 run(num_cp)] + [내용 run(text_cp)]. 폼 실측 구조 그대로."""
    return (f'<hp:endNote number="{n}"><hp:subList><hp:p id="0" paraPrIDRef="11">'
            f'<hp:run charPrIDRef="{num_cp}"><hp:ctrl><hp:autoNum num="{n}"/></hp:ctrl></hp:run>'
            f'<hp:run charPrIDRef="{text_cp}"><hp:t> </hp:t></hp:run>{LS}</hp:p>'
            f'</hp:subList></hp:endNote>')


def test_answer_charpr():
    new = "<hs:sec>" + "".join(_note(i, "21", "20") for i in (1, 2, 3)) + "</hs:sec>"
    old = "<hs:sec>" + "".join(_note(i, "22", "21") for i in (1, 2, 3)) + "</hs:sec>"
    chk(_answer_charpr(new) == "20", f"A 개정 폼 내용 charPr=20: {_answer_charpr(new)!r}")
    chk(_answer_charpr(old) == "21", f"A 25년 폼 내용 charPr=21: {_answer_charpr(old)!r}")
    chk(_answer_charpr("<hs:sec></hs:sec>") == "21", "A 미주 없음 → 폴백 21")
    # 폼 자체의 흔들림(중3 개정 폼은 뒤쪽 미주 번호 run 이 다른 charPr) — 내용 run 최빈값.
    mixed = "<hs:sec>" + _note(1, "21", "20") + _note(2, "21", "20") + _note(3, "23", "20") + "</hs:sec>"
    chk(_answer_charpr(mixed) == "20", "A 번호 run 이 섞여도 내용 run 기준")

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


def test_header_placeholders():
    def run(texts, values):
        sec = "<hs:sec>" + "".join(f"<hp:t>{t}</hp:t>" for t in texts) + "</hs:sec>"
        fp = _hwpx(sec)
        try:
            n = _fill_form_header(fp, values)
            return n, _sec_of(fp)
        finally:
            os.remove(fp)

    mid = {"학교": "침산중", "학년": "중2", "과목": "수학", "년도": "2026", "학기": "2",
           "구분": "중간"}
    n, got = run(["2025년 O학기 OO고사", "OO중 2학년 수학", "OO중 27년 O학기 OO고사 대비 (수학)",
                  "여기에 학원 로고 또는 이름"], mid)
    chk("<hp:t>2026년 2학기 중간고사</hp:t>" in got, f"B 시험명: {got}")
    chk("<hp:t>침산중 2학년 수학</hp:t>" in got, f"B 가운데(자리표시 OO 까지 치환): {got}")
    chk("<hp:t>침산중 26학년 2학기 중간고사 대비 (수학)</hp:t>" in got, f"B 꼬리말: {got}")
    chk("OO" not in got and "O학기" not in got, f"B 자리표시 O 잔존 0: {got}")
    chk("여기에 학원 로고 또는 이름" in got, "B 학원 로고 칸은 사람이 채운다(보존)")

    # 고1 폼 — "공통수학O" 를 한 덩어리로(안 그러면 '공통' 이 남는다). 표시명 공수2→공통수학2.
    hi1 = {"학교": "대진고", "학년": "고1", "과목": "공수2", "년도": "2025", "학기": "2",
           "구분": "기말"}
    n, got = run(["OO고 2학년 공통수학O", "OO고 25년 O학기 OO고사 대비 (공통수학O)"], hi1)
    chk("<hp:t>대진고 1학년 공통수학2</hp:t>" in got, f"B 고1 가운데: {got}")
    chk("<hp:t>대진고 25학년 2학기 기말고사 대비 (공통수학2)</hp:t>" in got, f"B 고1 꼬리말: {got}")
    chk("공통공통" not in got and "수학O" not in got, f"B '공통'·O 잔존 0: {got}")

    # 대수 폼 꼬리말은 '년' 이 빠져 있다("27 O학기") — 그래도 통째 치환.
    alg = {"학교": "강동고", "학년": "고2", "과목": "수1", "년도": "2025", "학기": "1",
           "구분": "기말"}
    n, got = run(["OO고 27 O학기 OO고사 대비 (대수)", "OO고 2학년 대수"], alg)
    chk("<hp:t>강동고 25학년 1학기 기말고사 대비 (수학1)</hp:t>" in got, f"B '년' 없는 꼬리말: {got}")
    chk("<hp:t>강동고 2학년 수학1</hp:t>" in got, f"B 대수 폼 가운데: {got}")

    # 확통 폼(학년 토큰 없는 과목 폼)을 고3 이 쓴다 — 학년은 값이 덮어쓴다.
    st3 = {"학교": "대진고", "학년": "고3", "과목": "확통", "년도": "2025", "학기": "1",
           "구분": "기말"}
    n, got = run(["OO고 2학년 확률과 통계", "OO고 27년 O학기 OO고사 대비 (확률과 통계)"], st3)
    chk("<hp:t>대진고 3학년 확률과 통계</hp:t>" in got, f"B 고3 확통: {got}")

    # 25년 폼 자리표시(빈칸형)도 그대로 통한다 + 꼬리말 "(정답)" 보존.
    n, got = run(["2024년 학기 고사", "고 1학년 수학", "중 25년 학기 고사 대비 (수학) (정답)"], mid)
    chk("<hp:t>2026년 2학기 중간고사</hp:t>" in got and "<hp:t>침산중 2학년 수학</hp:t>" in got,
        f"B 구 폼 무회귀: {got}")
    chk("대비 (수학) (정답)</hp:t>" in got, f"B 구 폼 (정답) 보존: {got}")

    # 미적분 번호는 과목명이다(과거 '미적분1'→'미적분' 강등 폐기).
    mj = dict(alg, 과목="미적1")
    n, got = run(["OO고 2학년 미적분1"], mj)
    chk("<hp:t>강동고 2학년 미적분1</hp:t>" in got, f"B 미적1 → 미적분1: {got}")


def test_range_placeholder():
    chk(_RANGE_PH_RE.search("<hp:t>시작 범위 ~ 끝 범위</hp:t>") is not None, "C 개정 자리표시 매칭")
    chk(_RANGE_PH_RE.search("<hp:t> ~ </hp:t>") is not None, "C 구 자리표시 매칭")
    chk(_RANGE_PH_RE.search("<hp:t>1 ~ 5</hp:t>") is None, "C 본문 범위표기는 미매칭")
    chk(_RANGE_PH_RE.search("<hp:t>시작 범위 ~ 끝 범위입니다</hp:t>") is None,
        "C 런 전체가 자리표시일 때만")
    for ph in ("시작 범위 ~ 끝 범위", " ~ "):
        fp = _hwpx(f"<hs:sec><hp:run charPrIDRef=\"18\"><hp:t>{ph}</hp:t></hp:run>"
                   "<hp:t>문항 1~5 는</hp:t></hs:sec>")
        try:
            n = _fill_exam_range(fp, "삼각비 ~ 대푯값과 산포도")
            got = _sec_of(fp)
        finally:
            os.remove(fp)
        chk(n == 1 and "<hp:t>삼각비 ~ 대푯값과 산포도</hp:t>" in got and "시작 범위" not in got,
            f"C 범위 치환({ph!r}): n={n} {got}")
        chk("<hp:t>문항 1~5 는</hp:t>" in got, "C 본문 물결 보존")
    # 머리말 채움(scope.txt 경로)도 같은 자리표시를 쓴다.
    fp = _hwpx("<hs:sec><hp:t>시작 범위 ~ 끝 범위</hp:t><hp:t>OO중 1학년 수학</hp:t></hs:sec>")
    try:
        _fill_form_header(fp, {"학교": "A중", "학년": "중1", "과목": "수학", "년도": "2025",
                               "학기": "1", "구분": "기말", "범위": "정수와 유리수 ~ 일차방정식"})
        got = _sec_of(fp)
    finally:
        os.remove(fp)
    chk("<hp:t>정수와 유리수 ~ 일차방정식</hp:t>" in got, f"C header_values['범위']: {got}")


def test_essay_meta_paragraph_boundary():
    def para(pp, inner):
        return f'<hp:p id="0" paraPrIDRef="{pp}" styleIDRef="0">{inner}{LS}</hp:p>'

    def meta(label, color):
        return para("11", f'<hp:run charPrIDRef="22"><hp:t><hp:markpenBegin color="{color}"/>'
                          f' [{label}]  <hp:markpenEnd/></hp:t></hp:run>')

    blank26 = para("26", '<hp:run charPrIDRef="20"/>')
    blank11 = para("11", '<hp:run charPrIDRef="20"/>')
    sub = para("26", '<hp:run charPrIDRef="20"><hp:t> 소문항 본문</hp:t></hp:run>')
    tok_so = para("11", f'<hp:run charPrIDRef="20"><hp:t>{_META_TOKEN_SO}</hp:t></hp:run>')
    tok_na = para("11", f'<hp:run charPrIDRef="20"><hp:t>{_META_TOKEN_NA}</hp:t></hp:run>')
    # 객관식 슬롯(살아있는 메타란 = 템플릿) + 빈 줄 + 서술형 소문항 + 답란 빈 줄 + 토큰 2줄 + 빈 줄
    sec = ("<hs:sec>" + meta("중단원", "#FF843A") + meta("난이도", "#42C7F1") + blank11
           + sub + blank26 + tok_so + tok_na + blank11 + "</hs:sec>")
    fp = _hwpx(sec)
    try:
        n = _inject_essay_meta(fp)
        got = _sec_of(fp)
    finally:
        os.remove(fp)
    chk(_META_TOKEN_SO not in got and _META_TOKEN_NA not in got, "D 토큰 0")
    chk(got.count("[중단원]") == 2 and got.count("[난이도]") == 2, f"D 메타란 2쌍: {got}")
    chk(got.count("<hp:p ") == got.count("</hp:p>"), "D 단락 태그 균형")
    # ⭐ 주입된 [중단원] 단락은 **토큰 단락의 문단모양(11)** — 앞 빈 단락(26)의 것이 아니다.
    import re
    pps = re.findall(r'<hp:p id="0" paraPrIDRef="(\d+)"[^>]*>(?:(?!</hp:p>).)*?\[중단원\]', got, re.S)
    chk(pps == ["11", "11"], f"D [중단원] 단락 paraPr: {pps}")
    # 토큰 바로 앞 빈 줄(답란 잔여)은 버린다 — 종전(우연한) 레이아웃을 명시적으로 유지.
    chk(got.count('paraPrIDRef="26"') == 1, f"D 토큰 앞 빈 단락 제거(소문항 줄만 26): {got}")
    # 토큰과 떨어진 빈 줄은 그대로.
    chk(got.count('<hp:run charPrIDRef="20"/>') == 2, "D 다른 빈 줄은 보존")
    chk(n >= 2, f"D 교체 건수: {n}")


def test_sub_marker():
    chk(_sub_marker(1, True) == "⑴" and _sub_marker(3, True) == "⑶", "E 글리프 ⑴⑶")
    chk(_sub_marker(20, True) == "⒇", "E 글리프 상한 ⒇")
    chk(_sub_marker(21, True) == "(21)", "E 21번째부터는 글리프가 없다 → (k)")
    chk(_sub_marker(2, False) == "(2)", "E 25년 폼 = (k)")
    # OCR 이 소문항 본문 머리에 ⑴ 를 남기면 우리 마커와 겹친다 → 제거.
    out = _strip_leading_submarker([_tb("⑴ 넓이를 구하시오.")])
    chk((out[0].value or "").startswith("넓이"), f"E ⑴ 접두 제거: {out[0].value!r}")


def run():
    for t in (test_answer_charpr, test_header_placeholders, test_range_placeholder,
              test_essay_meta_paragraph_boundary, test_sub_marker):
        t()
    if FAILS:
        print("FAIL:")
        for f in FAILS:
            print(" -", f)
        return 1
    print("OK test_form_generation (answer-charpr / header-placeholder / range / "
          "meta-para-boundary / sub-marker)")
    return 0


if __name__ == "__main__":
    sys.exit(run())
