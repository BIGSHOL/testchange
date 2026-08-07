# -*- coding: utf-8 -*-
"""웹 경로의 figure 해소가 GUI 워커와 **같은 결과**를 내는지 (stdlib·API 0원·COM 없음).

⭐ 2026-08-08 정합성 감사 blocker: 웹은 GUI 워커를 안 거치므로 `_resolve_figures` 가
실행되지 않았고, `content_parser` 가 ``type=="figure"`` 를 **무조건 None 으로 드롭**해
그림이 흔적도 없이 사라졌다. 게다가 그 안내 문구는 단순 안내가 아니라 **레이아웃 판정의
시그니처**다 — `_is_figure_note`(가운데정렬)·`_tail_start` walk-back(장산중 D3)·
`_post_has_stem` 배점 미루기(경일중 #19)가 전부 이 문구를 본다. 문구가 다르면 배점
위치까지 exe 와 갈린다.

실행: .venv\\Scripts\\python.exe tests/test_web_figure_resolve.py
"""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FAILED: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  OK   {label}")
    else:
        FAILED.append(label)
        print(f"  FAIL {label}" + (f" — {detail}" if detail else ""))


def _engine_resolve(envelope: dict) -> dict:
    """GUI 워커 `_resolve_figures` 의 render_figures=False 경로를 그대로 실행."""
    from gui.main_window import ConversionWorker

    w = ConversionWorker.__new__(ConversionWorker)   # __init__(Qt) 우회
    w.render_figures = False
    return w._resolve_figures(envelope, None, 1, 0)


def _sample() -> dict:
    """figure 가 본문·선택지·소문항에 모두 들어간 봉투."""
    return {
        "header": "",
        "questions": [
            {
                "number": 1, "score": 3,
                "contents": [
                    {"type": "text", "value": "그림과 같이"},
                    {"type": "figure", "value": "원 O 와 접선", "bbox": [0.1, 0.2, 0.9, 0.6]},
                    {"type": "text", "value": "일 때 값은?"},
                ],
                "choices": [
                    {"number": 1, "contents": [{"type": "figure", "value": "그래프 A"}]},
                    {"number": 2, "contents": [{"type": "equation", "value": "2"}]},
                ],
                "sub_questions": [
                    {"number": 1, "contents": [
                        {"type": "figure", "value": "전개도"},
                        {"type": "text", "value": "겉넓이를 구하시오."},
                    ]},
                ],
            },
            {"number": 2, "contents": [{"type": "text", "value": "그림 없음"}]},
        ],
    }


def test_same_as_engine() -> None:
    print("A. 웹 경로 figure 해소 == GUI 워커")
    from server.convert_cli import resolve_figures

    web_env, eng_env = _sample(), _sample()
    n = resolve_figures(web_env)
    eng = _engine_resolve(eng_env)

    check("치환 개수(본문1+선택지1+소문항1)", n == 3, f"n={n}")
    check("워커 결과와 완전히 동일", web_env["questions"] == eng["questions"],
          "순회 규칙 또는 문구가 다름")

    from gui.main_window import _FIGURE_NOTE_TEXT
    body = web_env["questions"][0]["contents"]
    check("figure 가 안내 텍스트로 치환됨",
          body[1] == {"type": "text", "value": _FIGURE_NOTE_TEXT}, str(body[1]))
    check("figure 없는 문항은 무변경",
          web_env["questions"][1] == _sample()["questions"][1])


def test_survives_parser() -> None:
    """해소하면 파서를 통과해 살아남고, 안 하면 사라진다 — 그게 blocker 의 핵심."""
    print("B. 파서 통과 여부")
    from server.convert_cli import resolve_figures
    from core.content_parser import parse_ocr_response
    from gui.main_window import _FIGURE_NOTE_TEXT

    raw = _sample()
    dropped = parse_ocr_response(copy.deepcopy(raw), page_number=1)
    txt_before = " ".join(
        b.value for q in dropped.questions for b in q.contents if getattr(b, "value", None))
    check("해소 안 하면 그림이 사라진다(현상 재현)",
          _FIGURE_NOTE_TEXT not in txt_before)

    fixed = _sample()
    resolve_figures(fixed)
    page = parse_ocr_response(fixed, page_number=1)
    txt_after = " ".join(
        b.value for q in page.questions for b in q.contents if getattr(b, "value", None))
    check("해소하면 그림자리가 본문에 남는다", _FIGURE_NOTE_TEXT in txt_after)

    # 선택지·소문항까지 살아남아야 한다.
    q = page.questions[0]
    ch_txt = " ".join(
        b.value for c in (q.choices or []) for b in c.contents if getattr(b, "value", None))
    check("선택지 그림도 살아남음", _FIGURE_NOTE_TEXT in ch_txt, ch_txt[:60])
    sub_txt = " ".join(
        b.value for s in (q.sub_questions or []) for b in s.contents
        if getattr(b, "value", None))
    check("소문항 그림도 살아남음", _FIGURE_NOTE_TEXT in sub_txt, sub_txt[:60])


def test_note_text_is_single_source() -> None:
    """문구를 손으로 적으면 레이아웃 판정이 조용히 깨진다 — 상수 참조를 강제."""
    print("C. 안내 문구 단일 출처")
    src = (ROOT / "server" / "convert_cli.py").read_text(encoding="utf-8")
    check("convert_cli 가 _FIGURE_NOTE_TEXT 를 import",
          "_FIGURE_NOTE_TEXT" in src and "from gui.main_window import" in src)
    check("문구를 하드코딩하지 않음", "※ 그림 자리" not in src)

    # 렌더러는 ContentBlock 을 받으므로 파서를 거친 실제 블록으로 확인한다.
    from gui.main_window import _FIGURE_NOTE_TEXT
    from core.hwp_com_writer import _is_figure_note
    from core.content_parser import parse_ocr_response
    from server.convert_cli import resolve_figures

    env = _sample()
    resolve_figures(env)
    blocks = parse_ocr_response(env, page_number=1).questions[0].contents
    notes = [b for b in blocks if _is_figure_note(b)]
    check("렌더러가 이 문구를 그림노트로 인식", len(notes) == 1,
          "레이아웃(가운데정렬·tail 경계·배점 미루기) 판정이 깨진다")


def main() -> int:
    print("웹 경로 figure 해소 회귀\n")
    for fn in (test_same_as_engine, test_survives_parser, test_note_text_is_single_source):
        fn()
        print()
    if FAILED:
        print(f"{len(FAILED)}건 FAIL:")
        for f in FAILED:
            print(f"  - {f}")
        return 1
    print("전부 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
