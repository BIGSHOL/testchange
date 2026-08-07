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

        out.write_text(
            f"SELFTEST OK (v{_ver}): {google.genai.__file__}\n{gem_line}\n{ds_line}\n",
            encoding="utf-8")
        return 0
    except Exception as e:
        import traceback
        out.write_text("SELFTEST FAIL:\n" + traceback.format_exc(), encoding="utf-8")
        return 1


def main():
    if "--selftest" in sys.argv:
        sys.exit(_selftest_imports())

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
