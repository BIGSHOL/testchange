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
import os
import json
import argparse
import atexit
import shutil
import tempfile
import time
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


def resolve_figures(envelope: dict, fig_dir: "Path | None" = None) -> int:
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
    drawn = 0

    def _to_png(b: dict):
        """figure 블록 → PNG 경로(없으면 None). **구조화 스펙 → SVG → 원본 크롭** 순.

        ⭐ 1순위는 `figure-spec`(FigureSpec v2) 이다 — 엔진(`core.figure_scene`)이
        컴파일하면서 **라벨을 자동 배치**한다(선·곡선·다른 라벨과의 충돌을 계산해 피함).
        모델이 손으로 좌표를 찍은 SVG 는 라벨이 선을 밟거나 서로 겹친다(사용자
        2026-08-20). 판정·컴파일은 엔진의 `_compile_structured_candidate` 를 **그대로
        재사용**한다 — 사본을 만들면 exe 경로와 갈라진다.

        ⭐ 그 결과(모델 생성물)는 **신뢰할 수 없으므로** 반드시 정제·검증을 거친다
        (`core.figure_quality.assess_svg` = 허용목록 기반 보안 경계 + 구조/픽셀 게이트).
        게이트를 못 넘으면 원본 크롭으로 폴백하고, 그것도 없으면 안내문구로 돌아간다
        (엔진 `figure_generator.render_figure` 와 같은 폴백 순서).
        """
        nonlocal drawn
        if fig_dir is None:
            return None
        import base64

        idx = drawn
        svg = b.get("svg")
        spec = b.get("spec")
        if (isinstance(svg, str) and svg.strip()) or spec:
            try:
                from core.figure_generator import (_compile_structured_candidate,
                                                   _svg_to_png_bytes)
                from core.figure_quality import assess_svg
                cand = {"svg": svg if isinstance(svg, str) else ""}
                if spec:
                    cand["figure_spec"] = spec
                    if isinstance(b.get("desc"), str):
                        cand["desc"] = b["desc"]
                svg2, err = _compile_structured_candidate(cand)
                if err:
                    sys.stderr.write(f"[convert] 도형 스펙 검증 실패 — SVG 로 폴백: {err}\n")
                    svg2 = svg if isinstance(svg, str) else ""
                res = assess_svg(svg2 or "", run_pixel_lint=True)
                if res.accepted and res.sanitized_svg:
                    png = _svg_to_png_bytes(res.sanitized_svg, width=_FIG_PNG_W)
                    if png:
                        out_png = fig_dir / f"fig{idx}.png"
                        out_png.write_bytes(png)
                        drawn += 1
                        return str(out_png)
                sys.stderr.write(
                    "[convert] 도형 SVG 게이트 탈락 — 원본 크롭으로 폴백 "
                    + str((res.security_issues or []) + (res.issues or []))[:160] + "\n")
            except Exception as e:  # noqa: BLE001 — 그림 실패가 변환을 막지 않는다
                sys.stderr.write(f"[convert] 도형 SVG 실패: {type(e).__name__}: {e}\n")
        crop = b.get("crop") or b.get("image")
        if isinstance(crop, str) and crop.strip():
            try:
                raw = crop.split(",", 1)[-1] if crop.startswith("data:") else crop
                out_png = fig_dir / f"fig{idx}_crop.png"
                out_png.write_bytes(base64.b64decode(raw))
                drawn += 1
                return str(out_png)
            except Exception as e:  # noqa: BLE001
                sys.stderr.write(f"[convert] 그림 크롭 저장 실패: {e}\n")
        return None

    def _contents(blocks):
        nonlocal n
        if not isinstance(blocks, list):
            return blocks
        out = []
        for b in blocks:
            if isinstance(b, dict) and b.get("type") == "figure":
                png = _to_png(b)
                if png:
                    out.append({"type": "image", "value": png})
                else:
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


# 그림 PNG 폭(px) — 96dpi 기준 ≈ 127mm. 폼 writer 가 단 너비·높이에 맞춰 다시 줄이므로
# (`_fit_image_width`) 여기서는 축소 손실이 없게 넉넉히 뽑는다.
_FIG_PNG_W = 480


def wants_figures(payload) -> bool:
    """그림을 **실제로 그려 넣을지** — 웹이 payload 로 지정한다(기본 꺼짐).

    ⭐ 플래그가 없으면 **기존 동작 그대로**(그림 자리 = 안내문구). 켜야만 켜진다 —
    폼 경로에 회귀를 만들지 않는다(사용자 2026-08-20 지시로 웹에서 켠다).
    """
    if not isinstance(payload, dict):
        return False
    if payload.get("renderFigures") or payload.get("render_figures"):
        return True
    return str(payload.get("figures") or "").strip().lower() in ("draw", "svg", "on")


# '폼 없이 2단' 을 뜻하는 layout 값들(웹이 보내는 표기 흔들림 흡수).
_PLAIN2_LAYOUTS = frozenset({"plain2", "plain2col", "plain-2col", "2col", "2단"})


def wants_plain_layout(payload) -> bool:
    """대수회 폼을 건너뛰고 **2단 기본 서식**으로 낼지 — 웹이 payload 로 지정한다.

    ⭐ 플래그가 없으면 **기존 동작 그대로**(파일명 규칙 → 대수회 폼). 즉 이 기능은
    켜야만 켜진다 — 폼 경로에 회귀를 만들지 않는다.
    """
    if not isinstance(payload, dict):
        return False
    if payload.get("noForm") or payload.get("no_form"):
        return True
    v = str(payload.get("layout") or "").strip().lower().replace(" ", "").replace("_", "")
    return v in _PLAIN2_LAYOUTS


def _render_plain_2col(document, info: dict, out_path: Path, show_answers: bool) -> Path:
    """폼 없이 **2단 기본 서식**으로 렌더 — 구현은 `core.plain_render`(exe GUI 와 공유).

    ⚠️ 여기서 렌더 인자를 다시 쓰지 말 것: 배포 exe(GUI)도 같은 함수를 부르므로
    사본을 만들면 "웹과 exe 결과가 다르다" 가 된다.
    """
    from core.form_registry import plain_form_path
    from core.plain_render import render_plain_2col

    tpl = plain_form_path()
    sys.stderr.write(
        f"[convert] 2단 기본 서식(폼 미사용) · 바탕="
        f"{Path(tpl).name if tpl else '(빈 새 문서)'}\n")
    return render_plain_2col(document, out_path, info=info, show_answers=show_answers)


def _render_engine_envelope(payload: dict, out_path: Path) -> Path:
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

    from models.exam_document import drop_answer_key_questions

    envelope = {
        "header": payload.get("header") or "",
        "questions": payload.get("questions") or [],
    }
    # ⭐ 답지(정답·해설) 페이지가 문항으로 들어온 것을 먼저 걷어낸다 — 유령 문항은 본문에
    # 채점기준을 찍을 뿐 아니라 서답형 수를 부풀려 정답면 라벨 재부여를 통째로 죽인다
    # (대륜고 공수2 사용자 보고 2026-08-20). 결정적 규칙이라 정상 시험지는 무변화.
    n_key_before = len(envelope["questions"])
    envelope["questions"], _dropped_key = drop_answer_key_questions(envelope["questions"])
    if _dropped_key:
        sys.stderr.write(
            f"[convert] 답지 페이지로 판정해 제외한 문항 {len(_dropped_key)}개"
            f" (봉투 {n_key_before} → {len(envelope['questions'])})\n")
    # ⭐ 파서에 넣기 **전에** figure 해소(엔진 워커와 같은 순서).
    #   · 그림 렌더 모드(웹이 `renderFigures` 지정): SVG(정제·검증) 또는 원본 크롭 → PNG
    #     → ``image`` 블록. 실패분만 안내문구로 남는다.
    #   · 기본: 종전대로 전부 안내문구(바이트 동일 경로).
    draw_figures = wants_figures(payload)
    fig_dir = None
    if draw_figures:
        fig_dir = Path(tempfile.mkdtemp(prefix="convfig_"))
        # 렌더가 끝날 때까지 파일이 살아 있어야 하므로 **프로세스 종료 시** 지운다
        # (convert_cli 는 변환 1건짜리 단명 자식 프로세스다).
        atexit.register(shutil.rmtree, str(fig_dir), True)
    n_fig = resolve_figures(envelope, fig_dir)
    n_drawn = len(list(fig_dir.glob("*.png"))) if fig_dir else 0
    if draw_figures:
        sys.stderr.write(f"[convert] 그림 렌더 — 삽입 {n_drawn}개 · 안내문구 {n_fig}개\n")
    page = parse_ocr_response(envelope, page_number=1)
    document = build_document([page])

    # 파일명 → 폼 + 머리말 값(학교·학년·과목·년도·학기·구분). GUI 와 동일.
    filename = payload.get("filename") or ""
    info = parse_filename(filename) if filename else {"valid": False}
    # ⭐ 웹이 '폼 없이 2단' 을 지정하면 폼 매칭 자체를 건너뛴다(대수회 슬롯 채우기 없음).
    plain = wants_plain_layout(payload)
    form_path = None if plain else (resolve_form(filename) if filename else None)
    header_values = info if info.get("valid") else None
    form_name = ("(2단 기본 서식)" if plain
                 else Path(form_path).name if form_path else "(기본 서식)")
    sys.stderr.write(
        f"[convert] 엔진 봉투: 문항 {len(envelope['questions'])} · "
        f"폼={form_name} · 그림자리 {n_fig}\n")
    # 부모(connector)가 응답 헤더로 웹에 전달할 진단 — "왜 이 서식으로 나왔나"가
    # 가장 흔한 질문이라, 폼 매칭 결과를 변환 로그에 남길 수 있게 한다.
    # ⚠️ **결과가 확정된 뒤에 쓴다**(적대리뷰 2026-08-10): 시도 전에 쓰면 폼 채움이
    # 실패해 기본 서식으로 떨어져도 diag 는 "폼=대수회…" 라고 **거짓 보고**하고,
    # 자식 stderr 는 성공(rc=0) 시 부모가 읽지 않아 폼 실패가 어느 채널에도 안 남는다
    # (경상여고 사고에서 폴백이 살아날수록 이 무음화가 잦아진다).
    def _diag(used_form: str, fallback_error: str = "") -> None:
        try:
            out_path.with_suffix(out_path.suffix + ".diag.json").write_text(
                json.dumps({
                    "questions": len(envelope["questions"]),
                    "form": used_form,
                    "form_matched": form_name,
                    "form_fallback_error": fallback_error,
                    "filename": filename,
                    "header_values": bool(header_values),
                    "figure_notes": n_fig,
                    "answer_key_dropped": len(_dropped_key),
                }, ensure_ascii=False),
                encoding="utf-8")
        except Exception:  # noqa: BLE001 — 진단 실패가 변환을 막지 않는다
            pass

    form_error = ""
    if form_path:
        from core.hwp_com import hwp_pids, reap_hwp
        # ⭐ 폼 채움을 **2회까지** 시도한다. COM 크래시(-2147417851 RPC_E_SERVERFAULT)는
        # 비결정적이고, 한 번 죽으면 그 인스턴스가 고아로 남아 **이어지는 렌더까지
        # 오염**된다(2026-08-10 사용자 PC 로그: 크래시 → Quit 실패 → .hwp 굽기 실패
        # → 500). 고아를 정리하고 한 번 더 해 보면 폼을 살릴 수 있다 — 실패해도
        # 잃는 건 시간뿐이고, 성공하면 사용자가 기본 서식 대신 대수회 폼을 받는다.
        _t0 = time.time()
        for _try in range(2):
            hwp_before = hwp_pids()
            try:
                # ⭐ 그림은 웹이 `renderFigures` 를 켰을 때만 실제로 그린다(2026-08-20
                # 사용자 지시). 켜져 있으면 위에서 SVG/크롭을 PNG 로 만들어 image 블록에
                # 실어 뒀고, writer 가 자리표시로 넣은 뒤 최종 단계에서 진짜 그림으로
                # 갈아끼운다(figure_embed.replace_placeholder_figures — 보안경고 없음).
                made = write_exam_to_form(document, form_path, out_path,
                                          header_values=header_values,
                                          render_figures=bool(n_drawn))
                _diag(form_name)
                return Path(made) if made else out_path
            except Exception as e:  # noqa: BLE001 — 폼 실패는 기본 서식으로 폴백(GUI 동일)
                form_error = f"{type(e).__name__}: {e}"[:300]
                sys.stderr.write(
                    f"[convert] 폼 채움 실패({_try + 1}/2): {e}\n")
                # ⚠️ **COM 크래시일 때만** 정리한다. PID 차집합에는 변환 중 사용자가
                # 직접 띄운 한글도 섞일 수 있어(작업이 분 단위) 무조건 죽이면 남의
                # 미저장 문서를 날린다(적대리뷰 2026-08-10). 일반 예외는 세션
                # 컨텍스트매니저가 Quit 하므로 고아가 안 남는다.
                if _is_com_crash(e):
                    try:
                        killed = reap_hwp(hwp_pids() - hwp_before)
                        if killed:
                            sys.stderr.write(f"[convert] 크래시 HWP {killed}개 정리\n")
                    except Exception:  # noqa: BLE001 — 정리 실패가 폴백을 막지 않는다
                        pass
                # ⚠️ 재시도가 커넥터 타임아웃(MATHGEN_HWP_TIMEOUT, 기본 360초)을 넘기면
                # **오히려 결과가 통째로 없어진다** — [폼 2회 + 기본 서식]이 예산을
                # 초과하기 때문. 크래시가 늦게 났으면 재시도를 포기하고 바로 폴백한다.
                elapsed = time.time() - _t0
                if _try == 0 and elapsed >= _FORM_RETRY_BUDGET_S:
                    sys.stderr.write(
                        f"[convert] 폼 재시도 생략 — 이미 {elapsed:.0f}초 소모"
                        f"(타임아웃 예산 보호)\n")
                    break
                if _try == 0:
                    time.sleep(1.0)      # COM 안정화(커넥터 재시도와 같은 간격)
        sys.stderr.write("[convert] 폼 채움 실패 → 기본 서식으로\n")

    # ⚠️ 기본 서식(폼 미매칭·폼 채움 실패) 경로에서도 **정답·해설을 살린다.**
    # `write_exam_to_hwp` 는 `show_answers` 가 켜져 있을 때만 정답면을 붙이는데,
    # 이걸 안 넘기면 **돈 들여 만든 정답·해설이 통째로 버려진다**(적대리뷰 2026-08-08).
    # 폼 경로는 미주·메타란에 직접 주입하므로 이 플래그와 무관하다.
    has_answers = any(
        q.answer or q.solution for page in document.pages for q in page.questions
    )
    if has_answers:
        sys.stderr.write("[convert] 기본 서식 — 정답·해설 페이지 포함\n")
    if plain:
        made = _render_plain_2col(document, info, out_path, has_answers)
        _diag(form_name)
        return made
    made = write_exam_to_hwp(document, out_path, show_answers=has_answers)
    _diag("(기본 서식)", form_error)
    return Path(made) if made else out_path


# 폼 채움 재시도를 포기하는 경과시간(초). 커넥터 타임아웃(기본 360초) 안에
# [폼 2회 + 기본 서식 렌더]가 끝나야 하므로, 첫 크래시가 이보다 늦게 나면 폴백한다.
_FORM_RETRY_BUDGET_S = int(os.environ.get("MATHGEN_FORM_RETRY_BUDGET", "90"))

# HWP COM 서버가 **죽었을 때** 나오는 HRESULT — 이때만 고아 프로세스를 정리한다.
_COM_CRASH_HRESULTS = frozenset({
    -2147417851,   # RPC_E_SERVERFAULT — 서버가 예외로 죽음(2026-08-10 실사고)
    -2147023174,   # RPC_S_SERVER_UNAVAILABLE
    -2147417848,   # RPC_E_DISCONNECTED
    -2146959355,   # CO_E_SERVER_EXEC_FAILURE
})


def _is_com_crash(e: BaseException) -> bool:
    """예외가 'HWP 프로세스가 죽었다' 는 신호인가(고아 정리 대상)."""
    args = getattr(e, "args", ()) or ()
    return bool(args) and args[0] in _COM_CRASH_HRESULTS


def _record_output(requested: Path, actual: Path) -> None:
    """진단 사이드카에 **실제 산출물 파일명**을 박는다(부모가 추측하지 않게).

    ⚠️⚠️ 부모(커넥터)가 산출물을 스스로 찾으면 자식과 규칙이 어긋난다. 실제 위험:
    HWP 가 ``SaveAs`` **도중** 죽으면 잘린 ``out.hwp`` 가 디스크에 남고 writer 는
    올바르게 ``.hwpx`` 로 폴백하는데, 부모가 요청 확장자를 먼저 집으면 **그 깨진 파일을
    성공으로 내보낸다**(사용자는 안 열리는 파일을 받고 로그엔 아무 표시도 없다 —
    적대리뷰 2026-08-10). 자식은 이미 답을 알고 있으므로 그대로 알려 준다.
    """
    p = requested.with_suffix(requested.suffix + ".diag.json")
    try:
        d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:  # noqa: BLE001
        d = {}
    if not isinstance(d, dict):
        d = {}
    d["output"] = actual.name
    try:
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def resolve_output(produced, requested: Path):
    """실제로 만들어진 산출물 경로(없으면 None).

    ⚠️ **`.hwp` 굽기가 실패하면 writer 가 `.hwpx` 로 떨어뜨린다** — HWP 가 크래시했거나
    Quit 이 실패한 뒤가 그렇다. 그때 요청 경로(`.hwp`)만 확인하면 "출력 파일이 없습니다"
    로 오판해 **변환 전체가 500** 이 되고, 사용자는 멀쩡히 만들어진 `.hwpx` 조차 못 받는다
    (2026-08-10 실사고: 폼 크래시 → 기본 서식 렌더 성공 → 굽기 실패 → exit 3).
    `.hwpx` 는 폼 바탕쪽 2단 세로선만 빠질 뿐 내용은 온전하므로 **전달하는 게 맞다**.
    """
    cands = []
    if produced:
        cands.append(Path(produced))
    cands.append(requested)
    if requested.suffix.lower() == ".hwp":
        cands.append(requested.with_suffix(".hwpx"))
        cands.append(requested.with_name(requested.stem + ".__work.hwpx"))
    for c in cands:
        try:
            if c.exists() and c.stat().st_size > 0:
                return c
        except OSError:
            pass
    return None


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
        produced = _render_engine_envelope(payload, out_path)
        actual = resolve_output(produced, out_path)
        if actual is None:
            sys.stderr.write("렌더는 끝났으나 출력 파일이 없습니다.\n")
            return 3
        _record_output(out_path, actual)
        if actual != out_path:
            # 확장자 폴백은 **실패가 아니다** — 커넥터가 이 파일을 그대로 내보낸다.
            sys.stderr.write(f"[convert] 산출물 확장자 폴백: {actual.name}\n")
        sys.stderr.write(f"OK: {actual} ({actual.stat().st_size} bytes)\n")
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

    # A 경로와 같은 규칙으로 산출물을 판정한다(mathgen 은 .hwpx 요청이라 폴백 후보가
    # 없지만, 0바이트 산출물을 성공으로 보고하던 구멍은 여기서도 막힌다).
    actual_b = resolve_output(None, out_path)
    if actual_b is None:
        sys.stderr.write("write_exam_to_hwp 완료했으나 출력 파일이 없습니다.\n")
        return 3
    out_path = actual_b
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
