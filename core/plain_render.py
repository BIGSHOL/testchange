# -*- coding: utf-8 -*-
"""폼 없이 **2단 기본 서식**으로 렌더 — 웹(커넥터)·배포 exe(GUI) 공용.

대수회 폼은 *슬롯 채우기*(미주 문항칸·①②③④⑤ 사전배치·정답면 container)라 구조가
맞는 폼에만 쓸 수 있다. 여기 경로는 반대로 **바탕만 물려받고 본문은 흘려 쓴다** —
학교에서 쓰는 평범한 2단 시험지 양식(`forms/plain2col/*.hwp`)이 머리말·용지·단 설정·
단 구분선을 제공하고, 문항은 `write_exam_to_hwp` 가 그 위에 이어 쓴다.

⚠️ **두 호출자가 같은 함수를 쓴다**(사본 금지): 웹은 `server/convert_cli`,
배포 exe 는 `gui/main_window`. 한쪽만 고치면 "웹과 exe 결과가 다르다" 가 된다 —
`_write_tail`/`_put_tail` 이원화로 한 라운드 헛돌았던 전례가 있다.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def plain_header_meta(info: dict | None) -> dict:
    """파일명 파싱 결과 → 2단 템플릿 머리말 토큰값(`{{제목}}`·`{{과목}}`).

    파일명이 규칙(`[학교][학년][과목][25-2-중간][출판사]`)에 안 맞으면 빈 dict —
    토큰이 빈칸으로 치환돼 머리말만 비고 변환은 그대로 진행한다(2026-06-16
    '규칙 미일치라고 차단하지 않는다' 합의와 같은 태도).
    """
    if not isinstance(info, dict) or not info.get("valid"):
        return {}
    grade = str(info.get("학년") or "")          # "중1" / "고2"
    gnum = grade[-1] if grade[-1:].isdigit() else ""
    parts = [str(info.get("학교") or "")]
    if gnum:
        parts.append(f"{gnum}학년")
    if info.get("학기"):
        parts.append(f"{info['학기']}학기")
    if info.get("구분"):
        parts.append(f"{info['구분']}고사")
    return {
        "title": " ".join(p for p in parts if p),
        "subject": str(info.get("과목") or ""),
        "schoolName": str(info.get("학교") or ""),
        "grade": f"{gnum}학년" if gnum else grade,
        "semester": str(info.get("학기") or ""),
    }


def has_answers(document) -> bool:
    """정답/해설이 하나라도 있는가 — 기본 서식은 이 플래그가 있어야 정답면을 붙인다.

    ⚠️ 안 넘기면 **돈 들여 만든 정답·해설이 통째로 버려진다**(적대리뷰 2026-08-08).
    """
    return any(q.answer or q.solution
               for page in document.pages for q in page.questions)


def render_plain_2col(document, out_path, info: dict | None = None,
                      show_answers: bool | None = None) -> Path:
    """폼 없이 2단으로 렌더. 바탕 템플릿이 있으면 그 위에, 없으면 빈 새 문서.

    - ⚠️ **`use_endnote=False`**: 미주(자동번호)로 두면 문서 끝에 **빈 미주 목록**
      (`1. 2. 3. …`)이 인쇄된다(실측). 대수회 폼은 그 미주가 답안칸이라 필요하지만
      평문 2단에는 쓸 자리가 없다 — mathgen 웹 경로가 평문 번호를 쓰는 이유와 같다.
    - `divider` 는 **템플릿이 없을 때만** — 템플릿에는 단 구분선이 이미 들어 있고,
      form_mode 에서는 후처리(`_apply_body_columns`)가 아예 돌지 않는다.
    """
    from core.form_registry import plain_form_path
    from core.hwp_com_writer import write_exam_to_hwp

    out_path = Path(out_path)
    tpl = plain_form_path()
    if show_answers is None:
        show_answers = has_answers(document)
    logger.info("2단 기본 서식 렌더 — 바탕=%s", Path(tpl).name if tpl else "(빈 새 문서)")
    made = write_exam_to_hwp(
        document, out_path,
        template_path=tpl,
        form_mode=bool(tpl),        # 템플릿 머리말/단 설정 사용, COM 헤더는 생략
        columns=2,
        divider=not tpl,
        use_endnote=False,
        header_meta=plain_header_meta(info),
        show_answers=show_answers,
    )
    return Path(made) if made else out_path
