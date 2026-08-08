# -*- coding: utf-8 -*-
"""배점 숫자 → 표시 문자열. **모든 소비자가 이걸 써야 한다.**

⭐ 왜 중립 모듈인가(2026-08-08 적대리뷰):
처음엔 `hwp_com_writer` 안에 두고 렌더 4곳에만 적용했는데, `score` 를 문자열로 만드는
소비자는 그 외에도 있었다 — **DeepSeek 프롬프트 2곳**(`solution_generator` 의 소문항
배점·문항 배점)과 HWP 미설치 폴백(`hwpx_writer`). 그래서 exe 는 모델에 `(배점 3.0점)`
을 보내고 웹은 `(배점 3점)` 을 보내, **생성되는 정답·해설이 갈리고 그게 그대로 .hwp 에
렌더**됐다. 렌더만 맞춰서는 소용이 없다.

`hwp_com_writer` 를 import 하면 렌더 스택(COM 계열)이 딸려 오므로, 프롬프트 생성기가
쓸 수 있도록 의존성 없는 모듈로 분리한다.
"""
from __future__ import annotations


def score_str(score) -> str:
    """정수값이면 소수점을 떼고, 소수배점은 그대로.

    ⭐ 두 가지를 동시에 고친다:
      ① **인쇄 원본과 다르다** — OCR 이 배점을 ``3.0`` 으로 주면 ``str(3.0)`` = "3.0" 이라
         ``[3.0점]`` 으로 찍힌다. 실제 시험지엔 "[3점]" 으로 인쇄돼 있다.
      ② **웹과 exe 가 갈린다** — JSON 은 ``3`` 과 ``3.0`` 을 타입으로 구분하지 못한다.
         exe 는 파이썬 json 이 파싱한 float 를 그대로 쓰지만, 웹은 HTTP JSON 을 두 번
         거치며 필연적으로 int 로 접힌다. 코드로는 재현 불가라 **표시 시점 정규화**가
         유일하게 양쪽을 같게 만드는 방법이다.

    소수배점(3.5·4.3)은 실제로 그렇게 인쇄되므로 **건드리지 않는다**.
    """
    try:
        f = float(score)
    except (TypeError, ValueError):
        return str(score)
    return str(int(f)) if f.is_integer() else str(score)
