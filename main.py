"""수학 시험지 → HWPX 변환 프로그램 진입점."""

import logging
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
PROJECT_ROOT = Path(__file__).parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def setup_logging():
    """로깅 설정."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
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
        from core.crop_detector import detect_crops, _detect_with_gemini  # noqa: F401
        out.write_text(f"SELFTEST OK: {google.genai.__file__}\n", encoding="utf-8")
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
            background: #1d2939;
            color: #ffffff;
            border: none;
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
