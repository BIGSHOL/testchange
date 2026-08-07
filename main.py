"""수학 시험지 → HWPX 변환 프로그램 진입점."""

import logging
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
PROJECT_ROOT = Path(__file__).parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def setup_logging():
    """로깅 설정 — 콘솔 + **영구 로그파일**(폴백·오류 원인 추적용, 사용자 요구 2026-06-05).

    windowed exe(console=False)는 콘솔이 없어 로그가 유실된다. exe 옆(frozen) 또는
    프로젝트 루트(dev)에 회전 로그파일(``시험지한글화.log``)을 두어, 어떤 폴백이
    작동했는지(측정 실패·크롭 폴백·OCR 재시도·폼 채움 실패 등) 사후 확인한다.
    """
    handlers: list = [logging.StreamHandler()]
    try:
        from logging.handlers import RotatingFileHandler
        log_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else PROJECT_ROOT
        fh = RotatingFileHandler(
            str(log_dir / "시험지한글화.log"),
            maxBytes=3_000_000, backupCount=3, encoding="utf-8")
        handlers.append(fh)
    except Exception:
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )


def _selftest_imports() -> int:
    """동결(frozen) exe의 핵심 의존성 import 자가진단(--selftest).

    GUI 없이 google.genai(Gemini 크롭)·anthropic·win32com 등이 동결 환경에서
    실제로 로드되는지 확인한다. 정상 0, 실패 1.
    """
    # 윈도우 exe(console=False)는 stdout이 없으므로 결과를 파일로 기록.
    out = Path(sys.executable).parent / "selftest_result.txt"
    try:
        idx = sys.argv.index("--selftest")
        if idx + 1 < len(sys.argv):
            out = Path(sys.argv[idx + 1])
    except ValueError:
        pass
    try:
        import google.genai  # noqa: F401
        from google.genai import types  # noqa: F401
        import google.auth, google.oauth2  # noqa: F401
        import anthropic, fitz, PySide6  # noqa: F401
        import resvg_py  # noqa: F401  (그림 재생성 SVG→PNG — Rust 확장 번들 확인)
        from core.crop_detector import detect_crops, _detect_with_gemini  # noqa: F401
        from core.figure_generator import render_figure  # noqa: F401
        # 정답·해설 자동 생성(DeepSeek REST) — requests 번들 확인 포함
        import requests  # noqa: F401
        from core.solution_generator import generate_solutions  # noqa: F401
        try:
            from _version import __version__ as _ver
        except Exception:
            _ver = "?"

        # ── frozen 환경에서 **실제 Gemini API 호출**까지 검증(import 만으론 SSL/데이터
        # 파일 누락에 의한 런타임 실패를 못 잡음 — 2026-06-05 배포본 크롭 0개 사례). ──
        gem_line = "GEMINI LIVE: 건너뜀(키 없음)"
        try:
            from utils.config import get_gemini_key
            _gk = get_gemini_key()
            if _gk:
                from PIL import Image, ImageDraw
                _im = Image.new("RGB", (600, 800), "white")
                _d = ImageDraw.Draw(_im)
                _d.rectangle([60, 80, 540, 240], outline="black", width=3)
                _d.text((80, 100), "1. test problem  x+y=2", fill="black")
                _boxes = _detect_with_gemini(_im, _gk)
                gem_line = f"GEMINI LIVE OK: {len(_boxes)} boxes"
        except Exception as ge:  # noqa: BLE001
            import traceback as _tb
            gem_line = "GEMINI LIVE FAIL: " + repr(ge) + "\n" + _tb.format_exc()

        # 정답·해설 생성 키 유무(라이브 호출은 과금이라 하지 않고 설정만 확인)
        try:
            from utils.config import DEEPSEEK_MODEL, get_deepseek_key
            ds_line = ("DEEPSEEK: 키 있음, model=" + DEEPSEEK_MODEL) if get_deepseek_key() \
                else "DEEPSEEK: 키 없음(정답·해설 자동 작성 비활성)"
        except Exception as de:  # noqa: BLE001
            ds_line = "DEEPSEEK CONFIG FAIL: " + repr(de)

        # ⭐ 단원 분류 어휘가 **번들에 실제로 실렸는지** — 빠지면 메타(소단원/중단원)가
        # 분류표 밖 자유 생성으로 조용히 퇴화한다. 빌드/배포 사고를 여기서 잡는다
        # (사용자 2026-08-07 "다른 PC 에서 빌드해도 같은 변환기").
        from core.topic_vocab import vocabulary
        _hi = vocabulary("고2", "기하")
        _mi = vocabulary("중2", "수학")
        if len(_hi) < 10 or len(_mi) < 10:
            raise RuntimeError(
                f"단원 분류 어휘 누락 — 고등 {len(_hi)}개 / 중등 {len(_mi)}개. "
                "data/topic_vocab.json 이 번들에 실리지 않았습니다(build.spec datas 확인).")
        vocab_line = f"TOPIC VOCAB OK: 고2 기하 {len(_hi)}개 / 중2 {len(_mi)}개"

        out.write_text(
            f"SELFTEST OK (v{_ver}): {google.genai.__file__}\n"
            f"{gem_line}\n{ds_line}\n{vocab_line}\n",
            encoding="utf-8")
        return 0
    except Exception as e:
        import traceback
        out.write_text("SELFTEST FAIL:\n" + traceback.format_exc(), encoding="utf-8")
        return 1


def _convert_headless(argv: list[str]) -> int:
    """GUI 없이 PDF 한 편을 변환한다(``--convert <PDF> [출력.hwp] [--solutions]``).

    배포 exe 를 **실제로 돌려** 결과를 확인하는 용도(사용자 2026-08-07 "실제 시험지로 exe
    돌려서 정답·해설 확인"). GUI 워커를 그대로 쓰되, 사람이 누르는 게이트(크롭 편집·
    미리보기)는 자동 승인한다 — 즉 **GUI 로 변환한 것과 같은 코드 경로**를 탄다.

    옵션:
      ``--solutions``   정답·해설·메타 자동 작성 켜기(과금). 없으면 config 값을 따름.
      ``--backend X``   OCR 엔진 고정(auto|gemini-flash|gemini-pro|claude).
    """
    from pathlib import Path as _P

    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print("사용법: 시험지한글화.exe --convert <입력.pdf> [출력.hwp] "
              "[--solutions] [--backend auto|gemini-flash|gemini-pro|claude]")
        return 2
    src = _P(args[0]).resolve()
    if not src.exists():
        print(f"입력 파일 없음: {src}")
        return 2
    out = _P(args[1]).resolve() if len(args) > 1 else src.with_name(src.stem + "_변환.hwp")

    backend = "auto"
    if "--backend" in argv:
        i = argv.index("--backend")
        if i + 1 < len(argv):
            backend = argv[i + 1]

    from utils.config import get_api_key, get_generate_solutions
    from core.form_registry import parse_filename, resolve_form
    from gui.main_window import ConversionWorker

    info = parse_filename(src.name)
    form = resolve_form(src.name)
    gen = True if "--solutions" in argv else get_generate_solutions()
    print(f"입력: {src.name}")
    print(f"폼  : {_P(form).name if form else '(기본 서식)'}")
    print(f"OCR : {backend} / 정답·해설 자동작성: {'켬' if gen else '끔'}")
    print(f"출력: {out}\n")

    worker = ConversionWorker(
        str(src), str(out), get_api_key(),
        form_path=form,
        header_values=(info if info.get("valid") else None),
        skip_first_page=False, use_crop=True, render_figures=False,
        skip_preview=True, ocr_backend=backend, generate_solutions=gen,
    )
    # 사람이 누르는 게이트 자동 승인 — 검출된 크롭을 그대로 사용.
    worker.crop_requested.connect(lambda pages: worker.set_crop_result([b for _img, b in pages]))
    worker.preview_requested.connect(lambda _p: worker.set_preview_result(True))
    # ⚠️ 배포 exe 는 console=False 라 **stdout 이 없다** — print 만 하면 진행 상황을 어디서도
    # 볼 수 없어 "멈춘 건지 도는 건지" 알 수 없다(실측 2026-08-07: OCR 후 해설 생성 대기가
    # 로그에 안 남아 hang 으로 오인). 워커 로그를 **파일에도** 남긴다(출력 옆 .log).
    trace = out.with_suffix(out.suffix + ".log")
    try:
        trace.write_text(f"# {src.name} 변환 시작\n", encoding="utf-8")
    except Exception:  # noqa: BLE001
        trace = None

    def _trace(line: str) -> None:
        # ⚠️ **파일 기록을 먼저** 한다. print 를 앞에 두면 cp949 콘솔에서 비ASCII
        # (em-dash ―·≈ 등)가 UnicodeEncodeError 를 내고, 그 예외 때문에 **파일 기록까지
        # 통째로 건너뛴다**(실측 2026-08-07: 비용 [USAGE] 줄이 통째로 유실).
        # build.spec 에서 고친 것과 같은 계열의 버그다.
        if trace is not None:
            try:
                with trace.open("a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            except Exception:  # noqa: BLE001
                pass
        try:
            print(line, flush=True)
        except Exception:  # noqa: BLE001 — 콘솔 인코딩이 못 찍는 문자(무해, 파일엔 남음)
            try:
                enc = getattr(sys.stdout, "encoding", None) or "utf-8"
                print(line.encode(enc, "replace").decode(enc, "replace"), flush=True)
            except Exception:  # noqa: BLE001
                pass

    worker.log.connect(lambda lv, msg: _trace(f"  [{lv}] {msg}"))
    worker.progress.connect(lambda pct, msg: _trace(f"  {pct:3d}% {msg}"))
    # 크롭 인식 실패 등 품질 경고도 남긴다 — 문항이 조용히 빠지는 것을 막는다.
    worker.quality_warning.connect(lambda pg, msg: _trace(f"  [품질] {msg}"))
    worker.ocr_warning.connect(lambda pg, msg: _trace(f"  [OCR] {msg}"))
    state = {"ok": False, "err": ""}
    worker.finished.connect(lambda path: state.update(ok=True))
    worker.error.connect(lambda e: state.update(err=e))

    from PySide6.QtCore import QCoreApplication
    _app = QCoreApplication.instance() or QCoreApplication(sys.argv[:1])  # 시그널 전달용
    worker.run()
    if state["err"]:
        _trace(f"[실패] {state['err']}")
        return 1
    if not out.exists():
        _trace(f"[실패] 출력 파일이 생성되지 않았습니다: {out}")
        return 1
    _trace(f"[완료] {out}  ({out.stat().st_size // 1024}KB)")
    return 0


def main():
    if "--selftest" in sys.argv:
        sys.exit(_selftest_imports())
    if "--convert" in sys.argv:
        setup_logging()
        i = sys.argv.index("--convert")
        sys.exit(_convert_headless(sys.argv[i + 1:]))

    setup_logging()

    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # 전역 스타일시트
    app.setStyleSheet("""
        * {
            font-family: "Malgun Gothic", "맑은 고딕", "Segoe UI", sans-serif;
        }
        QMainWindow, QDialog {
            background-color: #ffffff;
        }
        QLineEdit {
            border: 1px solid #d0d5dd;
            border-radius: 6px;
            padding: 8px 12px;
            font-size: 13px;
            background: #ffffff;
            color: #1d2939;
            selection-background-color: #0d6efd;
        }
        QLineEdit:focus {
            border: 1px solid #0d6efd;
        }
        QLineEdit:disabled {
            background: #f2f4f7;
            color: #98a2b3;
        }
        QPushButton {
            border: 1px solid #d0d5dd;
            border-radius: 6px;
            padding: 6px 16px;
            font-size: 13px;
            font-weight: 500;
            background: #ffffff;
            color: #344054;
        }
        QPushButton:hover {
            background: #f9fafb;
            border-color: #98a2b3;
        }
        QPushButton:pressed {
            background: #f2f4f7;
        }
        QPushButton:disabled {
            background: #f2f4f7;
            color: #98a2b3;
            border-color: #e4e7ec;
        }
        QProgressBar {
            border: 1px solid #e4e7ec;
            border-radius: 6px;
            background: #f2f4f7;
            text-align: center;
            font-size: 11px;
            color: #475467;
        }
        QProgressBar::chunk {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #0d6efd, stop:1 #4d94ff);
            border-radius: 5px;
        }
        QPlainTextEdit {
            border: 1px solid #e4e7ec;
            border-radius: 8px;
            padding: 8px;
            background: #f9fafb;
            color: #344054;
            font-size: 12px;
            selection-background-color: #0d6efd;
        }
        QScrollArea {
            border: none;
        }
        QToolTip {
            background-color: #ffffff;
            color: #1d2939;
            border: 1px solid #d0d5dd;
            border-radius: 4px;
            padding: 6px 10px;
            font-size: 12px;
        }
    """)

    from gui.main_window import MainWindow

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
