# -*- coding: utf-8 -*-
"""대수회 폼지(.hwp) 등록·해석.

학년·과목별 색상 폼(구조 동일, 색·머리말 과목만 다름)을 번들/폴더에서 찾아 목록화하고,
입력 파일명/문서 학년으로 맞는 폼을 자동 선택한다. 폼 채움은
``core/hwp_form_writer.write_exam_to_form`` 이 수행하며, 이 모듈은 "어떤 폼을
쓸지"만 결정한다.

폼 세대(파일명 규칙이 다르다 — 둘 다 읽는다):
  * **26년 개정 9종**(2026-10-06 교체): ``(중1용)``·``(중2용)``·``(중3용)``·``(고1용)``·
    ``(고2 대수)``·``(고2 미적분1)``·``(기하)``·``(미적분2)``·``(확통)`` + ``(색) (개정)``.
    선택과목 3종은 **과목별 폼**이고 학년 토큰이 없다(고2·고3 공용).
  * 25년 7종(구): ``(고2 수1용)``·``(고2 수2용)``·``(고2 선택과목용)`` … — 선택과목은 통합 1종.
    `<exe폴더>/forms/` 에 구 폼을 그대로 둔 사용자를 위해 계속 인식한다.

폼 위치(우선순위, 중복 파일명은 먼저 찾은 것):
  1) 번들 ``_MEIPASS/forms/`` (PyInstaller 동결 exe)
  2) exe 옆 ``<exe폴더>/forms/`` (재빌드 없이 폼 추가·교체용)
  3) 개발 ``<repo>/forms/``
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

# 폼 파일명의 괄호 토큰. ⚠️ 대괄호 머리 ``[26년 폼지 최종(10.05)]`` 안에도 괄호가 있어
# 대괄호 구간을 먼저 걷어낸 뒤 센다(안 그러면 날짜 ``(10.05)`` 가 첫 토큰으로 잡힌다).
_BRACKET_PART_RE = re.compile(r"\[[^\]]*\]")
_PAREN_RE = re.compile(r"\(([^()]*)\)")
# 폼 종류 토큰: "중2용" / "고1용" / "고2 수1용" / "고2 대수" / "기하" …
_FORM_TAG_RE = re.compile(r"^\s*(?:(중|고)\s*([1-3]))?\s*(.*?)\s*$")
# 색상이 아닌 꼬리 표식(색상 판정에서 제외) — "(개정)".
_NON_COLOR_MARKS = {"개정"}
# 입력 파일명 패턴 "[조암중][2]…" → 학교 + 학년숫자
_INPUT_HEAD_RE = re.compile(r"^\s*\[([^\]]*)\]\s*\[\s*([1-3])\s*\]")
# 본문/제목에 직접 박힌 학년 "중2"·"고1"
_GRADE_LITERAL_RE = re.compile(r"(중|고)\s*([1-3])")

_GRADE_ORDER = {"중1": 0, "중2": 1, "중3": 2, "고1": 3, "고2": 4, "고3": 5}
# 학년 토큰이 없는 과목 폼(기하·미적분2·확통)의 정렬 자리 — 고2 폼 뒤.
_ELECTIVE_ORDER = 4.5


@dataclass
class FormInfo:
    path: str
    grade: str          # "중2", "고2" … 학년 없는 과목 폼(기하 등)은 ""
    subtag: str         # 파일명에 적힌 과목 토큰 그대로 — "수1"·"대수"·"확통"·"선택과목" 또는 ""
    color: str          # "연두" …
    display: str        # 드롭다운 표시명
    subject: str = ""   # 표준 과목키 — "대수"·"미적분1"·"미적분2"·"기하"·"확률과통계",
    #                     구 통합 폼은 "선택과목", 학년 전용 폼(중N·고1)은 ""


def _base_dirs() -> list[Path]:
    dirs: list[Path] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            dirs.append(Path(meipass) / "forms")
        dirs.append(Path(sys.executable).parent / "forms")
    else:
        dirs.append(Path(__file__).resolve().parent.parent / "forms")
    return dirs


def _parse_form(path: Path) -> FormInfo:
    """폼 파일명 → FormInfo. 규칙에 안 맞으면 grade·subject 가 빈 채로(자동 매칭 제외)."""
    toks = [t.strip() for t in _PAREN_RE.findall(_BRACKET_PART_RE.sub("", path.stem))]
    grade, subtag, color = "", "", ""
    if toks:
        m = _FORM_TAG_RE.match(toks[0])
        if m and m.group(1):
            grade = m.group(1) + m.group(2)                 # "고" + "2"
        rest = (m.group(3) if m else toks[0]) or ""
        # 꼬리 "용"(중2용·수1용·선택과목용) 은 과목이 아니다.
        subtag = re.sub(r"\s+", "", re.sub(r"용$", "", rest.strip()))
        for t in toks[1:]:
            if t not in _NON_COLOR_MARKS and re.fullmatch(r"[가-힣]+", t):
                color = t
                break
    # 표준 과목키 — 구 폼의 "수1"·"수2" 도 같은 키로 모인다(_SUBJECT_ALIASES).
    subject = _SUBJECT_ALIASES.get(subtag, subtag)
    if subject in _HS1_SUBJECTS:
        subject = ""                                        # 고1 과목 = 학년 전용 폼
    if not grade and subject not in _FORM_SUBJECTS:
        subtag = subject = ""                               # 규칙 밖 이름 — 자동 매칭 제외
    label = (grade + (f" {subtag}" if subtag else "")).strip()
    display = (label or path.stem) + (f" ({color})" if color else "")
    return FormInfo(str(path), grade, subtag, color, display.strip(), subject)


def list_forms() -> list[FormInfo]:
    """등록된 폼 목록(학년 순). 같은 표시명은 한 번만."""
    seen: set[str] = set()
    forms: list[FormInfo] = []
    for d in _base_dirs():
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.hwp")):
            fi = _parse_form(p)
            key = fi.display or fi.path
            if key in seen:
                continue
            seen.add(key)
            forms.append(fi)
    forms.sort(key=lambda f: (
        _GRADE_ORDER.get(f.grade, _ELECTIVE_ORDER if f.subject else 99), f.subtag, f.color))
    return forms


def _school_level(school: str) -> str:
    """학교명 → 학교급("중"/"고"/""). **마지막** 등급 글자로 판정한다.

    학교명은 "…중"/"…고"(여중·여고 포함)로 끝나므로, 이름 **안**에 다른 등급
    글자가 섞여도(중앙고의 '중', 고성중의 '고') 마지막 글자가 학교급이다.
    과거 `"중" in school` 선행 검사는 "중앙고"(고등)를 중학교로 오판해 중2 폼이
    매칭됐다(corpus 자가발전 파일럿에서 발견, 2026-06-10).
    """
    pos_j = school.rfind("중")
    pos_g = school.rfind("고")
    if pos_j < 0 and pos_g < 0:
        return ""
    return "중" if pos_j > pos_g else "고"


def detect_grade(text: str) -> str:
    """입력 파일명/제목에서 학년("중2"·"고1")을 추정. 못 찾으면 ""."""
    if not text:
        return ""
    base = Path(text).name
    # 1) "[학교][학년]" 패턴 — 학교명의 중/고로 학교급 결정
    m = _INPUT_HEAD_RE.search(base)
    if m:
        school, num = m.group(1), m.group(2)
        lv = _school_level(school)
        if lv:
            return lv + num
    # 2) 문자열에 직접 박힌 "중2"·"고1"
    m = _GRADE_LITERAL_RE.search(base)
    if m:
        return m.group(1) + m.group(2)
    return ""


def match_form(grade: str, subject: str = "") -> str | None:
    """학년 + **표준 과목키**에 맞는 폼 경로. 없으면 None.

    과목 폼은 학년을 덮어써 쓸 수 있다 — 폼 구조(객관식/서술형/정답)는 학년 무관이고 학년
    라벨은 header_values 가 채운다. 그래서 고3 확통·미적분·기하도 과목 폼으로 간다(고3 전용
    폼이 없어 매칭 실패로 변환 불가였던 것, 2026-06-14).

    우선순위:
      1) 그 과목 전용 폼 — 같은 학년 > 학년 없는 폼(기하·미적분2·확통) > 같은 학교급 다른 학년
      2) (구 25년 폼) 미적분2·기하·확통 = 통합 ``선택과목`` 폼
      3) 학년 전용 폼(중N·고1) — 과목이 없거나 과목 폼을 못 찾았을 때
      4) 그 학년의 아무 폼(고2인데 과목 미상 — 종전 '첫 폼' 동작)
    """
    if not grade:
        return None
    forms = list_forms()
    level = grade[0]

    def _rank(f: FormInfo) -> int:
        return 0 if f.grade == grade else (1 if not f.grade else 2)

    def _pick(subj: str) -> str | None:
        # 학년 토큰 없는 과목 폼(기하·미적분2·확통)은 **고등** 폼이다 — 중등으로 새지 않게.
        cands = [f for f in forms
                 if f.subject == subj and (f.grade[0] if f.grade else "고") == level]
        return min(cands, key=_rank).path if cands else None

    if subject:
        hit = _pick(subject)
        if not hit and subject in _ELECTIVE_SUBJECTS:
            hit = _pick("선택과목")
        if hit:
            return hit
    cands = [f for f in forms if f.grade == grade and not f.subject]
    if not cands:
        cands = [f for f in forms if f.grade == grade]
    return cands[0].path if cands else None


def match_by_grade(grade: str, subtag: str = "") -> str | None:
    """(구 API) 학년 + 폼 태그("수1"·"수2"·"선택과목")로 폼 경로. `match_form` 위임."""
    return match_form(grade, _SUBJECT_ALIASES.get(subtag, subtag))


def resolve_auto(input_path: str) -> str | None:
    """입력 파일명으로 학년 추정 → 폼 경로(없으면 None)."""
    return match_by_grade(detect_grade(input_path))


# ── 폼 없이 2단 — 바탕 템플릿 ────────────────────────────────────
# 대수회 폼(슬롯 채우기)이 아니라 **바탕만 물려받는** 템플릿. 머리말·용지·단 설정·
# 단 구분선만 제공하고 본문은 write_exam_to_hwp 가 흘려 쓴다. 제작은
# `scripts/make_plain2col_form.py`(본문 비우기 + 개요번호 해제 + 머리말 토큰화).
#
# ⚠️ **`forms/` 바로 밑이 아니라 하위 폴더**에 둔다 — `list_forms()` 는 `*.hwp` 를
# 비재귀로 훑으므로, 여기 두면 대수회 폼 목록(자동 매칭 대상)에 섞이지 않는다.
_PLAIN_SUBDIR = "plain2col"


def plain_form_path() -> str | None:
    """'폼 없이 2단' 바탕 템플릿 경로. 없으면 None(템플릿 없이 빈 문서 2단)."""
    for d in _base_dirs():
        pd = d / _PLAIN_SUBDIR
        if not pd.is_dir():
            continue
        for p in sorted(pd.glob("*.hwp")) + sorted(pd.glob("*.hwpx")):
            return str(p)
    return None


# ── 파일명 규칙 파싱 (머리말 채움·폼 선택용) ─────────────────────────
# 규칙: 중등 [학교중][학년][시기][출판사] / 고등 [학교고][학년][시기][과목][출판사]
#   학년 = 1|2|3, 시기 = "25-1-중간"(년-학기-중간/기말), 과목 = 고등만(브래킷).
_BRACKET_RE = re.compile(r"\[([^\]]*)\]")
_TERM_RE = re.compile(r"(\d{2,4})\s*[-_.]\s*([12])\s*[-_.]\s*(중간|기말)")

# 고등 과목 정규화: 15개정 ↔ 22개정 혼재. 표준키로 통일 후 그 키로 폼을 고른다.
#   수1=대수 → 대수 폼 / 수2=미적분1 → 미적분1 폼 /
#   미적분(미적분2)·기하·확통 → 과목별 폼(26년 개정) 또는 통합 선택과목 폼(25년 구)
#   고1(공수1·공수2·수상·수하) → 고1폼(과목 없음)
_SUBJECT_ALIASES = {
    # 고1
    "공수1": "공통수학1", "공통수학1": "공통수학1", "수상": "공통수학1",
    "공수2": "공통수학2", "공통수학2": "공통수학2", "수하": "공통수학2",
    # 고2 수1 계열
    "수1": "대수", "수학1": "대수", "대수": "대수",
    # 고2 수2 계열(미적분Ⅰ) — 줄임말 "미적1"·로마숫자 "미적분I" 도 인식(미래엔황 등 출판사
    # 파일명이 "[미적1]" 로 줄여 쓰는데 별칭에 없어 과목 미인식→폼 자동선택 포기됐다, 2026-06-18).
    "수2": "미적분1", "수학2": "미적분1", "미적분1": "미적분1",
    "미적1": "미적분1", "미적분I": "미적분1", "미적분Ⅰ": "미적분1",
    # 선택과목(미적분Ⅱ=진로선택)
    "미적분": "미적분2", "미적분2": "미적분2",
    "미적2": "미적분2", "미적분II": "미적분2", "미적분Ⅱ": "미적분2",
    "기하": "기하",
    "확통": "확률과통계", "확률과통계": "확률과통계",
}
# 표준 과목 → (구) 폼 subtag. 25년 폼 3분류 그대로 — `parse_filename()["form_subtag"]` 의
# 값이라 소비자 호환을 위해 유지한다. 폼 선택 자체는 `form_subject`(표준 과목키)로 한다.
_SUBJECT_TO_SUBTAG = {
    "대수": "수1", "미적분1": "수2",
    "미적분2": "선택과목", "기하": "선택과목", "확률과통계": "선택과목",
}
_HS1_SUBJECTS = {"공통수학1", "공통수학2"}
# 과목별 폼이 따로 있는 선택과목(26년 개정). 구 폼에선 통합 `선택과목` 폼 하나로 받는다.
_ELECTIVE_SUBJECTS = {"미적분2", "기하", "확률과통계"}
# 폼 파일명에서 인정하는 과목키(학년 토큰 없는 폼의 유효성 판정).
_FORM_SUBJECTS = {"대수", "미적분1", "선택과목"} | _ELECTIVE_SUBJECTS


def parse_filename(input_path: str) -> dict:
    """입력 파일명을 규칙대로 파싱. 채움/폼선택에 필요한 값과 유효성 반환.

    반환: {valid, 학교, 학년("중2"/"고2"), 년도("2025"), 학기("1"), 구분("중간"),
           과목(표시명, 중등="수학"), form_subject(표준 과목키 — 폼 선택용),
           form_subtag(구 3분류 "수1"/"수2"/"선택과목"), raw_subject}
    """
    name = Path(input_path).stem
    out = {"valid": False, "학교": "", "학년": "", "년도": "", "학기": "",
           "구분": "", "과목": "", "form_subject": "", "form_subtag": "", "raw_subject": ""}
    toks = _BRACKET_RE.findall(name)
    if len(toks) < 3:
        return out
    school = toks[0].strip()
    level = _school_level(school)   # 마지막 등급 글자(중앙고='고', 고성중='중')
    gnum = toks[1].strip()
    if level not in ("중", "고") or gnum not in ("1", "2", "3"):
        return out
    out["학교"] = school
    out["학년"] = level + gnum
    # 시기
    joined = " ".join(toks)
    m = _TERM_RE.search(joined)
    if m:
        y = m.group(1)
        out["년도"] = ("20" + y) if len(y) == 2 else y
        out["학기"] = m.group(2)
        out["구분"] = m.group(3)
    # 과목
    if level == "중":
        out["과목"] = "수학"
        out["valid"] = bool(out["년도"])
        return out
    # 고등: 브래킷 중 과목 토큰 탐색
    for tk in toks[2:]:
        key = tk.strip().replace(" ", "")
        if key in _SUBJECT_ALIASES:
            std = _SUBJECT_ALIASES[key]
            out["raw_subject"] = tk.strip()
            out["과목"] = tk.strip()
            if std in _HS1_SUBJECTS:
                out["form_subtag"] = ""          # 고1폼
            else:
                out["form_subject"] = std
                out["form_subtag"] = _SUBJECT_TO_SUBTAG.get(std, "선택과목")
            break
    out["valid"] = bool(out["과목"] and out["년도"])
    return out


def resolve_form(input_path: str) -> str | None:
    """파일명 규칙 파싱 → (학년+과목) 맞는 폼 경로. 규칙 미일치/매칭 실패 시 None."""
    info = parse_filename(input_path)
    if not info["valid"]:
        return None
    return match_form(info["학년"], info["form_subject"])
