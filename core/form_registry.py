# -*- coding: utf-8 -*-
"""대수회 폼지(.hwp) 등록·해석.

학년별 색상 폼 7종(구조 동일, 색만 다름)을 번들/폴더에서 찾아 목록화하고,
입력 파일명/문서 학년으로 맞는 폼을 자동 선택한다. 폼 채움은
``core/hwp_form_writer.write_exam_to_form`` 이 수행하며, 이 모듈은 "어떤 폼을
쓸지"만 결정한다.

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

# 폼 파일명 안의 학년 토큰: "(중2용)", "(고1용)", "(고2 수1용)", "(고2 선택과목용)" …
_FORM_GRADE_RE = re.compile(r"\((중|고)\s*([1-3])\s*([^)]*?)\s*용\)")
# 색상: .hwp 직전의 한글 괄호 "(연두)", "(빨강)" …
_FORM_COLOR_RE = re.compile(r"\(([가-힣]+)\)\s*$")
# 입력 파일명 패턴 "[조암중][2]…" → 학교 + 학년숫자
_INPUT_HEAD_RE = re.compile(r"^\s*\[([^\]]*)\]\s*\[\s*([1-3])\s*\]")
# 본문/제목에 직접 박힌 학년 "중2"·"고1"
_GRADE_LITERAL_RE = re.compile(r"(중|고)\s*([1-3])")

_GRADE_ORDER = {"중1": 0, "중2": 1, "중3": 2, "고1": 3, "고2": 4, "고3": 5}


@dataclass
class FormInfo:
    path: str
    grade: str          # "중2", "고2" …
    subtag: str         # "수1", "수2", "선택과목" 또는 ""
    color: str          # "연두" …
    display: str        # 드롭다운 표시명


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
    name = path.name
    grade, subtag, color = "", "", ""
    m = _FORM_GRADE_RE.search(name)
    if m:
        grade = m.group(1) + m.group(2)            # "고" + "2"
        subtag = re.sub(r"\s+", "", m.group(3) or "")  # "수1"/"수2"/"선택과목"/""
    c = _FORM_COLOR_RE.search(path.stem)
    if c:
        color = c.group(1)
    label = grade + (f" {subtag}" if subtag else "")
    display = (label or path.stem) + (f" ({color})" if color else "")
    return FormInfo(str(path), grade, subtag, color, display.strip())


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
    forms.sort(key=lambda f: (_GRADE_ORDER.get(f.grade, 99), f.subtag, f.color))
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


def match_by_grade(grade: str, subtag: str = "") -> str | None:
    """학년(+선택과목 태그)에 맞는 폼 경로. 없으면 None.

    고2는 3종(수1/수2/선택과목)이라 학년만으론 모호 → subtag 우선, 없으면 첫 폼.
    """
    if not grade:
        return None
    cands = [f for f in list_forms() if f.grade == grade]
    if not cands and grade == "고3" and subtag == "선택과목":
        # 고3 선택과목(확통·미적분·기하)은 고2 선택과목 폼을 공유한다 — 폼 구조(객관식/서술형/
        # 정답)는 학년 무관, 학년 라벨은 header_values 로 덮어쓴다. 고3 전용 폼이 없을 때 폴백
        # (안 하면 고3 확통·미적분이 폼 매칭 실패로 변환 불가, 2026-06-14).
        cands = [f for f in list_forms() if f.grade == "고2" and f.subtag == "선택과목"]
    if not cands:
        return None
    if subtag:
        for f in cands:
            if f.subtag == subtag:
                return f.path
    return cands[0].path


def resolve_auto(input_path: str) -> str | None:
    """입력 파일명으로 학년 추정 → 폼 경로(없으면 None)."""
    return match_by_grade(detect_grade(input_path))


# ── 파일명 규칙 파싱 (머리말 채움·폼 선택용) ─────────────────────────
# 규칙: 중등 [학교중][학년][시기][출판사] / 고등 [학교고][학년][시기][과목][출판사]
#   학년 = 1|2|3, 시기 = "25-1-중간"(년-학기-중간/기말), 과목 = 고등만(브래킷).
_BRACKET_RE = re.compile(r"\[([^\]]*)\]")
_TERM_RE = re.compile(r"(\d{2,4})\s*[-_.]\s*([12])\s*[-_.]\s*(중간|기말)")

# 고등 과목 정규화: 15개정 ↔ 22개정 혼재. 표준키로 통일 후 폼 subtag 로 매핑.
#   수1=대수 → 수1폼 / 수2=미적분1 → 수2폼 / 미적분(미적분2)·기하·확통 → 선택과목폼
#   고1(공수1·공수2·수상·수하) → 고1폼(subtag 없음)
_SUBJECT_ALIASES = {
    # 고1
    "공수1": "공통수학1", "공통수학1": "공통수학1", "수상": "공통수학1",
    "공수2": "공통수학2", "공통수학2": "공통수학2", "수하": "공통수학2",
    # 고2 수1 계열
    "수1": "대수", "수학1": "대수", "대수": "대수",
    # 고2 수2 계열
    "수2": "미적분1", "수학2": "미적분1", "미적분1": "미적분1",
    # 선택과목
    "미적분": "미적분2", "미적분2": "미적분2",
    "기하": "기하",
    "확통": "확률과통계", "확률과통계": "확률과통계",
}
# 표준 과목 → 폼 subtag(고2). 고1 과목은 학년으로 고1폼 직행.
_SUBJECT_TO_SUBTAG = {
    "대수": "수1", "미적분1": "수2",
    "미적분2": "선택과목", "기하": "선택과목", "확률과통계": "선택과목",
}
_HS1_SUBJECTS = {"공통수학1", "공통수학2"}


def parse_filename(input_path: str) -> dict:
    """입력 파일명을 규칙대로 파싱. 채움/폼선택에 필요한 값과 유효성 반환.

    반환: {valid, 학교, 학년("중2"/"고2"), 년도("2025"), 학기("1"), 구분("중간"),
           과목(표시명, 중등="수학"), form_subtag, raw_subject}
    """
    name = Path(input_path).stem
    out = {"valid": False, "학교": "", "학년": "", "년도": "", "학기": "",
           "구분": "", "과목": "", "form_subtag": "", "raw_subject": ""}
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
                out["form_subtag"] = _SUBJECT_TO_SUBTAG.get(std, "선택과목")
            break
    out["valid"] = bool(out["과목"] and out["년도"])
    return out


def resolve_form(input_path: str) -> str | None:
    """파일명 규칙 파싱 → (학년+과목) 맞는 폼 경로. 규칙 미일치/매칭 실패 시 None."""
    info = parse_filename(input_path)
    if not info["valid"]:
        return None
    return match_by_grade(info["학년"], info["form_subtag"])
