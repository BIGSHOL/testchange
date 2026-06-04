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


def detect_grade(text: str) -> str:
    """입력 파일명/제목에서 학년("중2"·"고1")을 추정. 못 찾으면 ""."""
    if not text:
        return ""
    base = Path(text).name
    # 1) "[학교][학년]" 패턴 — 학교명의 중/고로 학교급 결정
    m = _INPUT_HEAD_RE.search(base)
    if m:
        school, num = m.group(1), m.group(2)
        if "중" in school:
            return "중" + num
        if "고" in school:
            return "고" + num
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
