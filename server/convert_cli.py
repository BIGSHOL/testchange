# -*- coding: utf-8 -*-
"""COM 격리 자식 — stdin의 변환 payload JSON → .hwp/.hwpx(COM) 저장.

부모 connector.py가 subprocess로 호출한다(ThreadingHTTPServer 워커 스레드의
COM 초기화 문제 회피 + 타임아웃/크래시 격리). Python 3.11(pywin32) 필수 — 3.13 불가.

⭐ **payload 두 가지를 받는다**(2026-08-08 — 웹 변환 서비스 E2E):

  A) 엔진 봉투  ``{"header","questions":[…],"filename"}``  ← 시험지 한글화 웹
     엔진 OCR JSON 그대로(snake_case). **exe(GUI)와 같은 렌더 경로** — 파일명으로
     대수회 폼을 고르고 ``write_exam_to_form`` 으로 채운다(머리말·정답면·메타란).
     폼이 안 잡히면 기본 서식(``write_exam_to_hwp``) — GUI 2026-06-16 합의와 동일.
  B) HwpPayload  ``{"problems":[…],"meta","style"}``     ← mathgen 웹
     camelCase typed-block. 종전대로 ``adapt_payload`` 경유(회귀 0).

구분은 ``questions`` 키 유무. COM-only: write_exam_to_hwpx(비-COM)는 레이아웃
깨짐으로 사용 금지(사용자 확정). is_hwp_available()도 호출 안 함(한글을 켜므로) —
바로 변환, 실패 시 예외 전파 → 부모 500.

실행: python -m server.convert_cli --in <payload.json> --out <path>
"""
import sys
import json
import argparse
import traceback
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ENGINE_ROOT = Path(__file__).resolve().parent.parent
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))


def resolve_figures(envelope: dict) -> int:
    """OCR JSON 의 ``figure`` 블록 → 그림자리 안내 텍스트(엔진 워커와 동일).

    ⭐⭐ **이 단계가 없으면 그림이 흔적도 없이 사라진다.** `content_parser` 는
    ``type == "figure"`` 를 무조건 None 으로 드롭하는데(주석: "워커(_resolve_figures)에서
    해소되어야 한다"), GUI 워커는 파서에 넣기 **전에** 이 치환을 한다
    (`gui/main_window._resolve_figures`, render_figures=False 경로).

    웹은 워커를 안 거치므로 커넥터가 대신 한다. 순회 규칙(contents·choices·
    sub_questions 재귀)과 문구를 엔진과 똑같이 맞춘다 — 문구는 단순 안내가 아니라
    **레이아웃 판정의 시그니처**다(`_is_figure_note` 가운데정렬, `_tail_start` walk-back,
    `_post_has_stem` 배점 미루기 게이트). 문구가 다르면 배점 위치까지 달라진다.

    Returns: 치환한 블록 수.
    """
    # ⚠️⚠️ **`gui.main_window` 를 import 하면 안 된다.** 배포 커넥터(agent.exe)는
    # `agent.spec` 이 PySide6 를 excludes 하므로, GUI 모듈을 건드리는 순간 figure 가 든
    # 시험지에서 ImportError 로 즉사한다(적대리뷰 2026-08-08 확인). 문구는 렌더러가 쓰는
    # `core.hwp_form_writer._FIGURE_NOTE` 와 **같은 문자열**이고 그쪽은 GUI 의존이 없다.
    from core.hwp_form_writer import _FIGURE_NOTE as _FIGURE_NOTE_TEXT

    n = 0

    def _contents(blocks):
        nonlocal n
        if not isinstance(blocks, list):
            return blocks
        out = []
        for b in blocks:
            if isinstance(b, dict) and b.get("type") == "figure":
                out.append({"type": "text", "value": _FIGURE_NOTE_TEXT})
                n += 1
            else:
                out.append(b)
        return out

    def _walk(q):
        if not isinstance(q, dict):
            return
        if "contents" in q:
            q["contents"] = _contents(q.get("contents"))
        for ch in q.get("choices") or []:
            if isinstance(ch, dict) and "contents" in ch:
                ch["contents"] = _contents(ch.get("contents"))
        for sub in q.get("sub_questions") or []:
            _walk(sub)

    for q in envelope.get("questions") or []:
        _walk(q)
    return n


def is_engine_envelope(payload) -> bool:
    """payload 가 엔진 OCR 봉투(``{header, questions}``)인가.

    ⭐ **판별은 여기 한 곳뿐**이다. 부모 connector.py 도 이 함수를 import 해서 쓴다 —
    양쪽이 따로 판정하면 어느 한쪽만 바뀌었을 때 확장자(.hwp/.hwpx)와 렌더 경로가
    조용히 어긋난다.
    """
    return isinstance(payload, dict) and isinstance(payload.get("questions"), list)


def _render_engine_envelope(payload: dict, out_path: Path) -> None:
    """엔진 OCR 봉투(``{header, questions, filename}``) → 대수회 폼 .hwp.

    **exe(GUI ConversionWorker)와 같은 렌더 경로**를 탄다 — 웹에서 변환한 결과가
    배포 exe 와 같아야 하기 때문. 폼 선택은 GUI 와 똑같이 **원본 파일명 규칙**
    (``[학교][학년][과목][25-2-중간][출판사]``)으로 하고, 규칙에 안 맞으면 차단하지
    않고 **기본 서식으로 그대로 렌더**한다(2026-06-16 사용자 합의).
    """
    from core.content_parser import parse_ocr_response, build_document
    from core.form_registry import parse_filename, resolve_form
    from core.hwp_com_writer import write_exam_to_hwp
    from core.hwp_form_writer import write_exam_to_form

    envelope = {
        "header": payload.get("header") or "",
        "questions": payload.get("questions") or [],
    }
    # ⭐ 파서에 넣기 **전에** figure → 안내 텍스트(엔진 워커와 같은 순서).
    n_fig = resolve_figures(envelope)
    page = parse_ocr_response(envelope, page_number=1)
    document = build_document([page])

    # 파일명 → 폼 + 머리말 값(학교·학년·과목·년도·학기·구분). GUI 와 동일.
    filename = payload.get("filename") or ""
    info = parse_filename(filename) if filename else {"valid": False}
    form_path = resolve_form(filename) if filename else None
    header_values = info if info.get("valid") else None
    form_name = Path(form_path).name if form_path else "(기본 서식)"
    sys.stderr.write(
        f"[convert] 엔진 봉투: 문항 {len(envelope['questions'])} · "
        f"폼={form_name} · 그림자리 {n_fig}\n")
    # 부모(connector)가 응답 헤더로 웹에 전달할 진단 — "왜 이 서식으로 나왔나"가
    # 가장 흔한 질문이라, 폼 매칭 결과를 변환 로그에 남길 수 있게 한다.
    try:
        out_path.with_suffix(out_path.suffix + ".diag.json").write_text(
            json.dumps({
                "questions": len(envelope["questions"]),
                "form": form_name,
                "filename": filename,
                "header_values": bool(header_values),
                "figure_notes": n_fig,
            }, ensure_ascii=False),
            encoding="utf-8")
    except Exception:  # noqa: BLE001 — 진단 실패가 변환을 막지 않는다
        pass

    if form_path:
        try:
            write_exam_to_form(document, form_path, out_path,
                               header_values=header_values, render_figures=False)
            return
        except Exception as e:  # noqa: BLE001 — 폼 채움 실패는 기본 서식으로 폴백(GUI 동일)
            sys.stderr.write(f"[convert] 폼 채움 실패 → 기본 서식으로: {e}\n")

    # ⚠️ 기본 서식(폼 미매칭·폼 채움 실패) 경로에서도 **정답·해설을 살린다.**
    # `write_exam_to_hwp` 는 `show_answers` 가 켜져 있을 때만 정답면을 붙이는데,
    # 이걸 안 넘기면 **돈 들여 만든 정답·해설이 통째로 버려진다**(적대리뷰 2026-08-08).
    # 폼 경로는 미주·메타란에 직접 주입하므로 이 플래그와 무관하다.
    has_answers = any(
        q.answer or q.solution for page in document.pages for q in page.questions
    )
    if has_answers:
        sys.stderr.write("[convert] 기본 서식 — 정답·해설 페이지 포함\n")
    write_exam_to_hwp(document, out_path, show_answers=has_answers)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="출력 .hwp/.hwpx 경로")
    ap.add_argument("--in", dest="infile", default=None,
                    help="입력 JSON 경로(없으면 stdin)")
    args = ap.parse_args()

    raw = (Path(args.infile).read_bytes()
           if args.infile else sys.stdin.buffer.read())
    if not raw:
        sys.stderr.write("빈 입력(payload 없음)\n")
        return 2
    payload = json.loads(raw)

    # ── A) 엔진 봉투(시험지 한글화 웹) — 대수회 폼 경로 ──
    if is_engine_envelope(payload):
        out_path = Path(args.out).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        _render_engine_envelope(payload, out_path)
        if not out_path.exists():
            sys.stderr.write("렌더는 끝났으나 출력 파일이 없습니다.\n")
            return 3
        sys.stderr.write(f"OK: {out_path} ({out_path.stat().st_size} bytes)\n")
        return 0

    # ── B) HwpPayload(mathgen 웹) — 종전 경로(회귀 0) ──
    from server.adapter import adapt_payload
    from core.content_parser import parse_ocr_response, build_document
    from core.hwp_com_writer import write_exam_to_hwp
    from core.template_headers import resolve_form_path

    envelope, meta, style = adapt_payload(payload)
    page = parse_ocr_response(envelope, page_number=1)
    document = build_document(
        [page],
        title=meta["title"],
        subject=meta["subject"],
        grade=meta["grade"],
    )

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # 고른 폼이 forms/<template>.hwpx 로 있으면 그 폼(머릿말/꼬릿말 픽셀완벽)을 쓰고
    # {{토큰}}을 시험지 정보로 치환. 없으면 COM 헤더(근사) 폴백 — 둘 다 회귀 0.
    # 2단 본문은 폼(본문에 헤더 박힘)과 양립 불가(§42-5) → 2단이면 폼 건너뛰고 COM 경로
    # (간단 머릿말 헤더 + 본문 2단). jeongtong 도 2단에선 이 경로로 2단 적용됨.
    form_path = None if style["columns"] == 2 else resolve_form_path(style["template"])
    write_exam_to_hwp(
        document,
        out_path,
        template_path=form_path,           # 폼 있으면 그 위에, 없으면 None
        form_mode=bool(form_path),
        template=style["template"],
        header_meta=meta,
        accent_color=style["accentColor"],
        columns=style["columns"],
        margins=style.get("margins"),
        divider=bool(style.get("divider")),  # 2단 컬럼 구분선(웹 columnDivider 토글)
        font=style.get("font"),  # 폰트팩 글꼴면 {serif, sans} (None 이면 함초롬 유지)
        show_answers=bool(style.get("show_answers")),  # 정답·해설 페이지 포함(웹 showAnswers, §44)
        quick_answer_only=bool(style.get("quick_answer_only")),  # 빠른 정답만(해설 생략)
        spacing=style.get("spacing"),  # 문항 간 세로 간격(웹 spacing px, §45). None 이면 기본 빈 줄
        show_chapter=bool(style.get("show_chapter")),  # 단원명 라벨(웹 showChapter, §45)
        use_endnote=False,  # 웹 내보내기: 평문 문항번호(미주 첨자·문서끝 미주목록 제거 — 완성도)
    )  # COM → save_hwpx → .hwpx

    if not out_path.exists():
        sys.stderr.write("write_exam_to_hwp 완료했으나 출력 파일이 없습니다.\n")
        return 3
    sys.stderr.write(f"OK: {out_path} ({out_path.stat().st_size} bytes)\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
