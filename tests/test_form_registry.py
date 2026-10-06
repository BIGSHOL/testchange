# 폼 자동매칭 학교급 판정 회귀 테스트 (stdlib only, HWP COM·API·키 0).
#   python tests/test_form_registry.py
#
# 학교명에 다른 등급 글자가 섞인 경우("중앙고"의 '중', "고성중"의 '고')의 학교급 오판 방지.
# 과거 `"중" in school` 선행 검사가 중앙고(고등)를 중2 폼에 매칭했다(corpus 파일럿, 2026-06-10).
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from core import form_registry
from core.form_registry import (FormInfo, _parse_form, _school_level, detect_grade,
                                match_form, parse_filename)


def run():
    fails = []

    def chk(cond, msg):
        if not cond:
            fails.append(msg)

    # 학교급: 마지막 등급 글자가 결정
    chk(_school_level("중앙고") == "고", "중앙고 → 고 (이름 안 '중'에 속지 않기)")
    chk(_school_level("고성중") == "중", "고성중 → 중 (이름 안 '고'에 속지 않기)")
    chk(_school_level("강동중") == "중", "강동중 → 중")
    chk(_school_level("경북여고") == "고", "경북여고 → 고")
    chk(_school_level("학남고") == "고", "학남고 → 고")
    chk(_school_level("대구초") == "", "초등(등급 글자 없음) → 빈 문자열")

    # detect_grade: [학교][학년] 패턴
    chk(detect_grade("[중앙고][2][확통][25-1-기말](원본).pdf") == "고2",
        "[중앙고][2] → 고2")
    chk(detect_grade("[고성중][1][25-1-기말](원본).pdf") == "중1",
        "[고성중][1] → 중1")
    chk(detect_grade("[강동중][1][25-1-기말] (원본).pdf") == "중1",
        "[강동중][1] → 중1")

    # parse_filename 의 level 도 동일 판정 사용
    info = parse_filename("[중앙고][2][확통][25-1-기말](원본).pdf")
    chk(info["학년"] == "고2", "parse_filename [중앙고][2] → 고2")
    chk(info["valid"], "parse_filename [중앙고] valid")

    # 미적분 줄임말 과목 인식(경상여고 미적1, 2026-06-18): '미적1'→미적분1(수2폼),
    # '미적2'→미적분2(선택과목). 별칭 누락으로 valid=False→폼 자동선택 포기됐던 회귀.
    mj1 = parse_filename("[경상여고][2][미적1][26-1-중간][미래엔황] (원본).pdf")
    chk(mj1["valid"] and mj1["학년"] == "고2" and mj1["form_subtag"] == "수2",
        f"parse_filename [미적1] → 고2/수2: valid={mj1['valid']} subtag={mj1['form_subtag']!r}")
    mj2 = parse_filename("[OO고][2][미적2][25-2-기말].pdf")
    chk(mj2["valid"] and mj2["form_subtag"] == "선택과목",
        f"parse_filename [미적2] → 선택과목: subtag={mj2['form_subtag']!r}")

    # ── 26년 개정 폼(2026-10-06 교체) — 파일명 규칙이 바뀌었다 ──────────────────
    # 과목 폼은 '용' 이 없고("(고2 대수)"), 선택과목 3종은 학년 토큰도 없다("(기하)").
    # 색상은 맨 끝이 아니라 "(개정)" 앞 — 맨 끝 괄호를 색으로 읽으면 전부 '개정'이 된다.
    def pf(name):
        return _parse_form(Path(name))

    N = "[대수회][26년 폼지 최종(10.05)] "
    for name, grade, subject, color in [
        ("(중1용) (남색) (개정).hwp", "중1", "", "남색"),
        ("(중3용) (빨강) (개정).hwp", "중3", "", "빨강"),
        ("(고1용) (파란) (개정).hwp", "고1", "", "파란"),
        ("(고2 대수) (초록) (개정).hwp", "고2", "대수", "초록"),
        ("(고2 미적분1) (보라) (개정).hwp", "고2", "미적분1", "보라"),
        ("(기하) (남색) (개정).hwp", "", "기하", "남색"),
        ("(미적분2) (남색) (개정).hwp", "", "미적분2", "남색"),
        ("(확통) (남색) (개정).hwp", "", "확률과통계", "남색"),
    ]:
        f = pf(N + name)
        chk((f.grade, f.subject, f.color) == (grade, subject, color),
            f"개정 폼 {name}: {(f.grade, f.subject, f.color)!r} ≠ {(grade, subject, color)!r}")
    # 대괄호 머리의 날짜 "(10.05)" 를 폼 종류 토큰으로 읽지 않는다.
    chk(pf(N + "(중2용) (연두) (개정).hwp").display == "중2 (연두)", "표시명 = '중2 (연두)'")
    # 25년 폼(구) 파일명도 계속 읽는다 — <exe폴더>/forms 에 구 폼을 둔 설치.
    O = "[대수회][25년 폼지 최종(01.09)] "
    for name, grade, subject, color in [
        ("(고2 수1용) (초록).hwp", "고2", "대수", "초록"),
        ("(고2 수2용) (보라).hwp", "고2", "미적분1", "보라"),
        ("(고2 선택과목용) (남색).hwp", "고2", "선택과목", "남색"),
        ("(중2용) (연두).hwp", "중2", "", "연두"),
    ]:
        f = pf(O + name)
        chk((f.grade, f.subject, f.color) == (grade, subject, color),
            f"구 폼 {name}: {(f.grade, f.subject, f.color)!r}")
    # 규칙 밖 이름은 자동 매칭 대상이 아니다(학년·과목 모두 빈 값).
    odd = pf("아무이름.hwp")
    chk(odd.grade == "" and odd.subject == "", "규칙 밖 폼 이름 → 매칭 제외")

    # 과목 표준키(폼 선택용). 구 3분류(form_subtag)는 소비자 호환으로 유지.
    for fn, subj in [("[A고][2][수1][25-1-기말].pdf", "대수"),
                     ("[A고][2][대수][26-1-중간].pdf", "대수"),
                     ("[A고][2][수2][25-1-중간].pdf", "미적분1"),
                     ("[A고][2][미적분][25-2-중간].pdf", "미적분2"),
                     ("[A고][3][확통][25-1-기말].pdf", "확률과통계"),
                     ("[A고][2][기하][25-2-중간].pdf", "기하"),
                     ("[A고][1][공수2][25-2-기말].pdf", ""),
                     ("[A중][2][25-1-기말].pdf", "")]:
        got = parse_filename(fn)["form_subject"]
        chk(got == subj, f"form_subject {fn} → {got!r} (기대 {subj!r})")

    # 폼 고르기 — 실제 forms/ 폴더와 무관하게 목록을 갈아끼워 규칙만 검증한다.
    def with_forms(names, fn):
        saved = form_registry.list_forms
        form_registry.list_forms = lambda: [_parse_form(Path(n)) for n in names]
        try:
            return fn()
        finally:
            form_registry.list_forms = saved

    new9 = [N + s for s in ("(중1용) (남색) (개정).hwp", "(중2용) (연두) (개정).hwp",
                            "(중3용) (빨강) (개정).hwp", "(고1용) (파란) (개정).hwp",
                            "(고2 대수) (초록) (개정).hwp", "(고2 미적분1) (보라) (개정).hwp",
                            "(기하) (남색) (개정).hwp", "(미적분2) (남색) (개정).hwp",
                            "(확통) (남색) (개정).hwp")]
    for grade, subj, want in [("중2", "", "(중2용)"), ("고1", "", "(고1용)"),
                              ("고2", "대수", "(고2 대수)"), ("고2", "미적분1", "(고2 미적분1)"),
                              ("고2", "기하", "(기하)"), ("고2", "확률과통계", "(확통)"),
                              # 고3 선택과목 — 학년 없는 과목 폼이 받는다(전용 폼 없음).
                              ("고3", "확률과통계", "(확통)"), ("고3", "미적분2", "(미적분2)"),
                              # 고3 인데 대수 — 같은 학교급의 과목 폼(학년은 머리말이 덮어쓴다).
                              ("고3", "대수", "(고2 대수)")]:
        got = with_forms(new9, lambda: match_form(grade, subj)) or ""
        chk(want in got, f"개정 9종 match_form({grade},{subj!r}) → {Path(got).name!r}")
    chk(with_forms(new9, lambda: match_form("중3", "기하")) is not None
        and "(중3용)" in with_forms(new9, lambda: match_form("중3", "기하")),
        "중등은 과목 폼으로 새지 않는다(학교급 다름 → 학년 폼)")
    old7 = [O + s for s in ("(고2 수1용) (초록).hwp", "(고2 수2용) (보라).hwp",
                            "(고2 선택과목용) (남색).hwp", "(고1용) (파란).hwp",
                            "(중1용) (남색).hwp", "(중2용) (연두).hwp", "(중3용) (빨강).hwp")]
    for grade, subj, want in [("고2", "대수", "수1용"), ("고2", "미적분1", "수2용"),
                              ("고2", "기하", "선택과목용"), ("고3", "확률과통계", "선택과목용"),
                              ("고1", "", "고1용"), ("중1", "", "중1용")]:
        got = with_forms(old7, lambda: match_form(grade, subj)) or ""
        chk(want in got, f"구 7종 match_form({grade},{subj!r}) → {Path(got).name!r}")
    chk(with_forms([], lambda: match_form("고2", "대수")) is None, "폼 0종 → None(2단 서식)")
    chk(isinstance(pf(N + "(기하) (남색) (개정).hwp"), FormInfo), "FormInfo 반환")

    # ── 구·신 폼이 섞인 폴더 = **새 세대 우선** (Codex 리뷰 2026-10-06) ──────────────
    # 구 폼을 안 지우고 새 폼만 넣는 게 흔한 설치 실수다. 파일명 정렬로는 `[25년…` 이 앞이라
    # 25년 폼이 이겼다. 세대 = 대괄호 머리의 (연도, 월, 일).
    chk(pf(N + "(중2용) (연두) (개정).hwp").gen == (26, 10, 5), "세대 판독(26년 10.05)")
    chk(pf(O + "(중2용) (연두).hwp").gen == (25, 1, 9), "세대 판독(25년 01.09)")
    chk(pf("아무이름.hwp").gen == (0, 0, 0), "세대 미상 = (0,0,0)")
    mixed = old7 + new9
    for grade, subj, want in [("중2", "", "26년"), ("고1", "", "26년"),
                              # 표시명이 달라 둘 다 목록에 남는 쌍(고2 수1 ↔ 고2 대수)도 새 폼.
                              ("고2", "대수", "(고2 대수)"), ("고2", "미적분1", "(고2 미적분1)"),
                              # 과목 전용 폼이 있으면 구 통합 선택과목 폼보다 먼저.
                              ("고2", "확률과통계", "(확통)"), ("고3", "기하", "(기하)")]:
        got = with_forms(mixed, lambda: match_form(grade, subj)) or ""
        chk(want in got, f"구·신 혼재 match_form({grade},{subj!r}) → {Path(got).name!r}")
    # list_forms 의 표시명 중복 제거도 새 세대를 남긴다(실제 폴더로 확인).
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        for nm in (O + "(중2용) (연두).hwp", N + "(중2용) (연두) (개정).hwp",
                   O + "(고2 선택과목용) (남색).hwp"):
            (Path(td) / nm).write_bytes(b"")
        saved = form_registry._base_dirs
        form_registry._base_dirs = lambda: [Path(td)]
        try:
            got = form_registry.list_forms()
        finally:
            form_registry._base_dirs = saved
    j2 = [f for f in got if f.display == "중2 (연두)"]
    chk(len(j2) == 1 and "26년" in j2[0].path, f"list_forms 중복 = 새 세대: {[f.path for f in j2]}")
    chk(any(f.subject == "선택과목" for f in got), "겹치지 않는 구 폼은 그대로 남는다")
    # 같은 세대가 두 폴더에 있으면 먼저 찾은 폴더(번들 > exe 옆 > 개발) 것 — 종전 규칙.
    with tempfile.TemporaryDirectory() as t1, tempfile.TemporaryDirectory() as t2:
        for td in (t1, t2):
            (Path(td) / (N + "(중2용) (연두) (개정).hwp")).write_bytes(b"")
        saved = form_registry._base_dirs
        form_registry._base_dirs = lambda: [Path(t1), Path(t2)]
        try:
            got = form_registry.list_forms()
        finally:
            form_registry._base_dirs = saved
        chk(len(got) == 1 and Path(got[0].path).parent == Path(t1),
            "같은 세대 = 먼저 찾은 폴더")

    if fails:
        print("FAIL:")
        for f in fails:
            print(" -", f)
        return 1
    print("test_form_registry: all OK")
    return 0


if __name__ == "__main__":
    sys.exit(run())
