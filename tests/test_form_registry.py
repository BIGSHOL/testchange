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

from core.form_registry import _school_level, detect_grade, parse_filename


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

    if fails:
        print("FAIL:")
        for f in fails:
            print(" -", f)
        return 1
    print("test_form_registry: all OK")
    return 0


if __name__ == "__main__":
    sys.exit(run())
