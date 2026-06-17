#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""자가발전 corpus 검수 — **결정적 lint**(API 0원, 비전 대조 전 1차 게이트).

REVIEW_PROTOCOL.md 의 4단계(JSON lint)·6단계(렌더 XML lint)를 자동화한다. 이번 중앙고
검수에서 사람 눈으로 놓쳤던 결함 클래스를 **기계로 강제 검출**해 회귀를 막는다.

사용:
  python scripts/corpus_lint.py --json "corpus/<시험지>/ocr"      # OCR JSON 규약
  python scripts/corpus_lint.py --xml  out.hwpx                    # 렌더 결과 XML
  python scripts/corpus_lint.py --all  "corpus/<시험지>" out.hwpx  # 둘 다

위반이 있으면 stderr 로 보고 + exit 1. 깨끗하면 exit 0.
"""
from __future__ import annotations

import json
import os
import re
import sys
import zipfile

try:
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 검사 결과 레벨: FAIL = 출력 깨짐(차단), WARN = 알려진 한계/권장(보고만, 통과).
FAIL, WARN = "FAIL", "WARN"


# ── JSON 규약 검사 (self-OCR 출력이 파이프라인 규약을 지키는지) ──────────────
_SCORE_IN_TEXT = re.compile(r'\[\s*(?:총\s*)?\d+(?:\.\d+)?\s*점')
_ESSAY_LABEL_IN_TEXT = re.compile(r'\[\s*(서술형|서답형|단답형)')


def lint_json(ocr_dir: str) -> list[tuple[str, str]]:
    """OCR JSON(p{n}_merged.json) 규약 위반 목록 [(level, msg)]."""
    issues: list[tuple[str, str]] = []
    files = sorted(f for f in os.listdir(ocr_dir)
                   if re.match(r"p\d+_merged\.json$", f))
    if not files:
        return [(FAIL, f"[json] {ocr_dir}: p*_merged.json 없음")]
    label_types: set[str] = set()
    for fn in files:
        try:
            data = json.load(open(os.path.join(ocr_dir, fn), encoding="utf-8"))
        except Exception as e:
            issues.append((FAIL, f"[json] {fn}: 파싱 실패 {e}"))
            continue
        for q in data.get("questions", []):
            if not isinstance(q, dict):
                issues.append((FAIL, f"[json] {fn}: 비-dict question"))
                continue
            num = q.get("number", "?")
            is_essay = not q.get("choices")
            texts = " ".join(b.get("value", "") for b in q.get("contents", [])
                             if isinstance(b, dict) and b.get("type") == "text")
            for m in _ESSAY_LABEL_IN_TEXT.finditer(texts):
                label_types.add(m.group(1))
            if not is_essay:
                chs = q.get("choices", [])
                # 그림 선택지(figure)면 선택지 텍스트가 적을 수 있어 2개 미만만 FAIL
                if len(chs) < 2:
                    issues.append((FAIL, f"[json] #{num}: 객관식 선택지 {len(chs)}개(<2)"))
                for ch in chs:
                    if not ch.get("contents"):
                        issues.append((FAIL, f"[json] #{num} 보기{ch.get('number')}: 빈 선택지"))
            if not q.get("score") and _SCORE_IN_TEXT.search(texts):
                issues.append((FAIL, f"[json] #{num}: score 필드 없음(본문에 [N점] 만)"))
            for b in q.get("contents", []):
                if isinstance(b, dict) and b.get("type") == "figure" and not b.get("bbox"):
                    issues.append((WARN, f"[json] #{num}: figure bbox 없음(그림 미렌더 예고)"))
            if is_essay and _ESSAY_LABEL_IN_TEXT.search(texts) and not q.get("label_type"):
                issues.append((WARN, f"[json] #{num}: 서답형 label_type 필드 없음(권장)"))
    # 서술형·단답형 혼합은 **정상**(능인고 수1 등) — 파이프라인이 문항별 유형으로 본문·정답
    # 라벨을 맞춘다. 단 서답형/서술형(같은 뜻 철자 변형) 혼용은 OCR 비일관 신호 → WARN.
    if {"서답형", "서술형"} <= label_types:
        issues.append((WARN, f"[json] 서답형/서술형 철자 혼용: {label_types} (한쪽으로 통일 권장)"))
    return issues


# ── 렌더 XML 검사 (출력 hwpx 의 결정적 결함) ─────────────────────────────────
_META_TOKENS = ("소단원자리표식QZX", "난이도자리표식QZX")
# 자모 혼입 = **조합용 첫가끝 자모(U+1100-11FF)** — 정상 텍스트엔 안 나오고 깨진 입력의 표식.
# 호환 자모(U+3130-318F: ㄱㄴㄷ…)는 보기 항목 라벨로 **정상** 사용되므로 제외(오탐 방지).
_JAMO_RE = re.compile(r"[ᄀ-ᇿ]")
# 타이핑 혼입 = 렌더 중 사용자 키입력이 숨김 COM 문서로 새 단독 호환자모 런(학산중 #1 'ㄷ',
# 강동중 낱자모 계열). 보기 라벨 'ㄷ. 가로…'는 한 런에 마침표+내용이 붙어 단독이 아니므로
# (정상 렌더 검증) **호환자모 1글자가 통째 한 hp:t 런**일 때만 혼입으로 판정(비결정 — 재렌더로 해소).
_LONE_JAMO_RE = re.compile(r"<hp:t[^>]*>([㄰-㆏ᄀ-ᇿ])</hp:t>")
# ⚠️ 위 단독 검사는 **호환자모+음절** 혼입(혜화여고 수2 'ㅔ서')은 못 잡는다 — 'ㅔ서'는 2글자라
# 단독 아니고, ㅔ(U+3154)는 호환자모라 _JAMO_RE(조합자모만) 도 통과 → 오염 렌더가 PASS 했다.
# 핵심: 정상 한글은 hp:t 를 **호환 모음 자모**(ㅏ-ㅣ U+314F-3163)로 **시작하지 않는다**(보기 라벨은
# ㄱㄴㄷ 자음이라 별개). 그래서 hp:t 가 호환 모음 자모로 시작하면(뒤에 뭐가 오든) 타이핑 혼입.
_LEAD_VOWEL_JAMO_RE = re.compile(r"<hp:t[^>]*>([ㅏ-ㅣ])")
_DUP_SCORE_RE = re.compile(r"\[\s*\d+\s*점\s*\][^<\[]{0,4}\[\s*\d+\s*점\s*\]")


def lint_xml(hwpx_path: str) -> list[tuple[str, str]]:
    """렌더된 hwpx 의 section XML 결함 목록 [(level, msg)]."""
    issues: list[tuple[str, str]] = []
    try:
        z = zipfile.ZipFile(hwpx_path)
    except Exception as e:
        return [(FAIL, f"[xml] {hwpx_path}: 열기 실패 {e}")]
    secs = [n for n in z.namelist() if re.search(r"section\d+\.xml$", n)]
    if not secs:
        return [(FAIL, f"[xml] {hwpx_path}: section XML 없음")]
    full = "".join(z.read(n).decode("utf-8") for n in secs)
    # ⚠️ 메타토큰·라벨 검사는 **태그 제거 후**(연속 문자열) 한다 — COM 저장이 토큰/라벨을
    # 여러 <hp:t> run 으로 비결정 쪼개면(효성중 B-1·대진고 문서화) raw 연속 count 가 0 이 돼
    # **오염 렌더가 PASS** 하던 게이트 우회(적대리뷰 A-4). 배점중복 검사와 동일 방식.
    stripped = re.sub(r"<[^>]+>", "", full)
    for tok in _META_TOKENS:
        c = stripped.count(tok)
        if c:
            issues.append((FAIL, f"[xml] 메타란 토큰 평문 노출: {tok} ×{c}"))
    for t in re.findall(r"<hp:t[^>]*>([^<]*)</hp:t>", full):
        if _JAMO_RE.search(t):
            issues.append((FAIL, f"[xml] 자모 혼입 런: {t!r}"))
    # 단독 호환자모 런 = 렌더 중 타이핑 혼입(학산중 #1 'ㄷ'). 보기 라벨 'ㄷ. …'는 마침표+내용이
    # 같은 런에 붙어 안 걸린다. 비결정이므로 재렌더로 해소(jamo grep 0 확인).
    for j in _LONE_JAMO_RE.findall(full):
        issues.append((FAIL, f"[xml] 단독 자모 런(타이핑 혼입 의심 — 재렌더): {j!r}"))
    # 호환 모음 자모로 시작하는 런 = 타이핑 혼입(혜화여고 수2 'ㅔ서' — 자모+음절이라 단독검사 회피).
    for j in _LEAD_VOWEL_JAMO_RE.findall(full):
        issues.append((FAIL, f"[xml] 모음자모 선두 런(타이핑 혼입 의심 — 재렌더): {j!r}"))
    # 서술형·단답형 혼합은 정상(문항별 유형). 서답형/서술형 철자 혼용만 동기화 실패 신호(FAIL).
    labels = set(re.findall(r"\[\s*(서술형|서답형|단답형)", stripped))
    if {"서답형", "서술형"} <= labels:
        issues.append((FAIL, f"[xml] 서답형/서술형 철자 혼용(동기화 실패): {labels}"))
    # '정답' 페이지 증발 검사 — 꼬리말 "(정답)" 은 정답 페이지가 증발해도 **항상 남아** 단어
    # 존재만 보면 무력하다(적대리뷰 A-4). 꼬리말 패턴을 먼저 지우고, 정답 **container**(텍스트
    # '정답' 이 그 안에 있음, CLAUDE.md) 의 본문 '정답' 이 남아야 통과로 본다.
    answer_probe = stripped.replace("(정답)", "")
    if "정답" not in answer_probe:
        issues.append((FAIL, "[xml] '정답' 블록 없음(정답 페이지 증발 가능 — 꼬리말 제외)"))
    for m in _DUP_SCORE_RE.finditer(re.sub(r"<[^>]+>", "", full)):
        issues.append((FAIL, f"[xml] 배점 중복: {m.group(0)!r}"))
    return issues


def main(argv: list[str]) -> int:
    mode = argv[0] if argv else ""
    issues: list[tuple[str, str]] = []
    if mode == "--json" and len(argv) >= 2:
        issues = lint_json(argv[1])
    elif mode == "--xml" and len(argv) >= 2:
        issues = lint_xml(argv[1])
    elif mode == "--all" and len(argv) >= 3:
        issues = lint_json(os.path.join(argv[1], "ocr")) + lint_xml(argv[2])
    else:
        sys.stderr.write(__doc__)
        return 2
    fails = [m for lv, m in issues if lv == FAIL]
    warns = [m for lv, m in issues if lv == WARN]
    for m in fails:
        sys.stderr.write(f"  FAIL {m}\n")
    for m in warns:
        sys.stderr.write(f"  WARN {m}\n")
    if fails:
        sys.stderr.write(f"corpus-lint: {len(fails)} FAIL, {len(warns)} WARN — 차단\n")
        return 1
    sys.stderr.write(f"corpus-lint: PASS ({len(warns)} WARN)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
