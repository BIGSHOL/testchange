"""PySide6 메인 윈도우 모듈.

드래그앤드롭, 파일 선택, 변환 진행률, 설정 관리를 포함합니다.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QThread, QObject
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.pdf_handler import (
    detect_and_correct_rotation,
    get_supported_extensions,
    is_pdf,
    load_image,
    page_source_kinds,
    pdf_to_images,
)
from core.ocr_engine import OCREngine, validate_ocr_response
from core.crop_detector import detect_crops, CropBox
from core.figure_generator import render_figure
from core.quality_checker import check_image_quality
from core.content_parser import parse_ocr_response, build_document
from core.hwpx_writer import write_exam_to_hwpx
from core.hwp_com import is_hwp_available
from core.hwp_form_writer import write_exam_to_form
from core.plain_render import render_plain_2col   # 폼 없이 2단(웹·exe 공용 구현)
from core.form_registry import resolve_form, parse_filename
from gui.preview_dialog import PreviewDialog, PageInfo
from utils.config import get_output_dir

logger = logging.getLogger(__name__)

# ⭐ 인식 엔진 **고정**(2026-08-07, 사용자) — 드롭다운을 없애고 Gemini Flash 로 못박는다.
# 기존 "auto" 는 페이지 품질로 Flash/Pro 를 분기했는데, 실측상 대부분 Flash 로 갔고
# (오성중·학남고·함지고 전부) Pro 는 5배 비싸다. 정답·해설은 DeepSeek 고정(solution_generator).
# ⚠️ 트레이드오프: 손글씨·저품질 스캔에서 Pro 가 더 충실했는데 그 경로를 안 쓰게 된다.
_FIXED_OCR_BACKEND = "gemini-flash"

# 크롭 OCR 병렬 처리 동시 실행 수(①). 너무 크면 API 레이트리밋, 작으면 속도 이득 적음.
_OCR_WORKERS = 6


class _FatalApiError(RuntimeError):
    """계속 진행해도 소용없는 API 오류(사용 한도 초과·키 무효) — 변환을 즉시 중단한다."""


# 한도 초과/키 무효 신호. **일시적 레이트리밋(재시도로 풀림)과 구분**해야 한다 —
# 429 라도 "spending cap"·"quota exceeded" 면 이번 달 내내 실패하므로 중단이 맞다.
_FATAL_API_PATTERNS = (
    "spending cap", "monthly spending", "quota exceeded", "exceeded your quota",
    "resource_exhausted", "insufficient balance", "insufficient_quota",
    "api key not valid", "api_key_invalid", "invalid_api_key",
    "permission_denied", "unauthorized", "401",
)


def _is_fatal_api_error(msg: str) -> bool:
    """복구 불가 API 오류인가(한도 초과·키 무효). 일시적 429/503 은 False."""
    m = (msg or "").lower()
    if not any(p in m for p in _FATAL_API_PATTERNS):
        return False
    # RESOURCE_EXHAUSTED 는 일시적 레이트리밋에도 쓰인다 — 한도/쿼터 문구가 함께 있을 때만 치명.
    if "resource_exhausted" in m and not any(
            p in m for p in ("spending cap", "monthly", "quota")):
        return False
    return True


def _fatal_api_message(reason: str) -> str:
    """치명 오류 원인 → 사용자가 바로 행동할 수 있는 안내문."""
    r = (reason or "").lower()
    if "spending cap" in r or "monthly" in r or "quota" in r or "resource_exhausted" in r:
        return ("Gemini 사용 한도를 초과했습니다 — 이번 달 설정한 지출 한도에 도달했습니다.\n\n"
                "· AI Studio(ai.studio/spending)에서 한도를 올리거나\n"
                "· 다음 달 한도가 초기화될 때까지 기다려 주세요.\n\n"
                "변환을 중단합니다(계속 진행해도 모든 문항이 실패합니다).")
    if "balance" in r:
        return ("DeepSeek 잔액이 부족합니다 — 계정에 충전한 뒤 다시 시도해 주세요.\n\n"
                "변환을 중단합니다.")
    return ("API 키가 유효하지 않습니다 — config.json 의 키를 확인해 주세요.\n\n"
            "변환을 중단합니다.")

# 그림 렌더링 OFF 일 때 figure 자리에 넣는 안내 문구(SVG 생성 대신). 폼 경로 _FIGURE_NOTE 와 통일.
_FIGURE_NOTE_TEXT = "※ 그림 자리 — 원본에서 이 영역을 캡처해 여기에 붙여넣으세요"

# 체크박스 스타일 + QToolTip 시인성 보정. 위젯 인라인 color 가 그 위젯 툴팁 글씨색으로
# 새어(어두운 글씨) 어두운 배경과 겹쳐 안 보이는 Qt 특성을, QToolTip 규칙을 함께 명시해
# 차단한다(흰 배경·진한 글씨·옅은 테두리). (사용자 보고 2026-06-08: 툴팁 글씨 안 보임.)
_CHECK_QSS = (
    "QCheckBox { font-size: 12px; color: #475467; } "
    "QToolTip { color: #1d2939; background-color: #ffffff; "
    "border: 1px solid #d0d5dd; padding: 6px 10px; }"
)


# 모델별 토큰 단가(USD / 1M tok) = (입력, 출력). 캐시읽기=입력의 0.1배, 캐시쓰기(5분)=입력의
# 1.25배. (대략치 — 정확 단가는 각 콘솔 기준. 비용계산 참고용, 사용자 2026-06-08.)
# Gemini 는 Sonnet 대비 5~7배 저렴(2026-06-16 라우팅 도입). flash < pro.
_PRICE = {"opus": (15.0, 75.0), "sonnet": (3.0, 15.0), "haiku": (1.0, 5.0),
          "gemini-pro": (1.25, 5.0), "gemini-flash": (0.30, 2.50)}


def _price_for(model: str) -> tuple[float, float]:
    """모델명 → (입력단가, 출력단가). Gemini/Claude 자동 판별."""
    m = (model or "").lower()
    if "gemini" in m:
        return _PRICE["gemini-flash"] if "flash" in m else _PRICE["gemini-pro"]
    if "opus" in m:
        return _PRICE["opus"]
    if "haiku" in m:
        return _PRICE["haiku"]
    return _PRICE["sonnet"]


def _as_hwpx_path(path: str) -> str:
    """HWP 미설치 폴백용 — 출력 경로를 .hwpx 로 바꾼다.

    기본 출력은 .hwp(폼 바탕쪽=2단 가운데 구분선 보존, 2026-07-24)지만 XML 생성기
    (`write_exam_to_hwpx`)는 .hwpx 만 만들 수 있다. 확장자를 안 바꾸면 hwpx 내용이
    .hwp 이름으로 저장돼 한글이 못 연다.
    """
    p = Path(path)
    return str(p.with_suffix(".hwpx")) if p.suffix.lower() != ".hwpx" else path


def _unique_output_path(path: str) -> str:
    """출력 경로가 이미 있으면 윈도우식으로 ``stem (1).ext``·``stem (2).ext`` … 를 붙여
    충돌 없는 새 경로를 돌려준다(덮어쓰기 방지, 사용자 2026-06-09)."""
    p = Path(path)
    if not p.exists():
        return str(p)
    stem, suffix, parent = p.stem, p.suffix, p.parent
    i = 1
    while True:
        cand = parent / f"{stem} ({i}){suffix}"
        if not cand.exists():
            return str(cand)
        i += 1


def _log_token_usage(exam_path: str, usage: dict, model: str | None = None) -> str:
    """시험지 1건의 토큰 사용량·예상비용을 로그 + ``토큰사용.csv`` 에 기록. 요약 문자열 반환.

    `model` 로 단가를 결정한다(없으면 CLAUDE_MODEL). 다중 백엔드(2026-06-16)면 엔진별로
    호출해 모델별 비용을 따로 집계·기록한다.
    """
    if not usage or not usage.get("calls"):
        return ""
    if not model:
        from utils.config import CLAUDE_MODEL
        model = CLAUDE_MODEL
    in_rate, out_rate = _price_for(model)
    inp, out = usage["input"], usage["output"]
    cc, cr = usage["cache_create"], usage["cache_read"]
    cost = (inp * in_rate + cc * in_rate * 1.25 + cr * in_rate * 0.1
            + out * out_rate) / 1_000_000
    krw = cost * 1500          # 환율 1500원/USD(사용자 2026-06-08)
    name = Path(exam_path).name if exam_path else "?"
    summary = (f"토큰 사용 — 입력 {inp:,} · 출력 {out:,} · 캐시(쓰기 {cc:,}/읽기 {cr:,}) · "
               f"호출 {usage['calls']}회 · 예상 ${cost:.4f} (₩{krw:,.0f}) ({model})")
    logger.info("[USAGE] %s | %s", name, summary)
    _append_usage_csv(exam_path, model, inp, out, cc, cr, usage["calls"], cost, krw)
    return summary


def _append_usage_csv(exam_path: str, model: str, inp: int, out: int, cc: int,
                      cr: int, calls: int, cost: float, krw: float) -> None:
    """``토큰사용.csv`` 한 줄 누적(로그파일과 같은 폴더). 헤더 1회.

    OCR(Gemini/Claude)·해설(DeepSeek) **양쪽이 같이 기록**돼야 시험지당 실제 총비용을
    추적할 수 있다(과거엔 OCR 만 기록해 총비용의 절반이 빠졌다, 2026-08-07).
    """
    try:
        import csv
        from datetime import datetime
        log_dir = (Path(sys.executable).parent if getattr(sys, "frozen", False)
                   else Path(__file__).resolve().parent.parent)   # 프로젝트 루트(gui/..)
        csv_fp = log_dir / "토큰사용.csv"
        new = not csv_fp.exists()
        with open(csv_fp, "a", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["시각", "시험지", "모델", "입력토큰", "출력토큰",
                            "캐시쓰기", "캐시읽기", "호출수", "예상USD", "예상KRW"])
            w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        Path(exam_path).name if exam_path else "?", model,
                        inp, out, cc, cr, calls, f"{cost:.4f}", f"{krw:.0f}"])
    except Exception as e:  # noqa: BLE001
        logger.warning("토큰 CSV 기록 실패(무시): %s", e)


# ─── 백그라운드 변환 워커 ────────────────────────────────────

class ConversionWorker(QObject):
    """백그라운드 스레드에서 변환 수행."""

    progress = Signal(int, str)    # (진행률%, 메시지) — 진행바·상태라벨 실시간 갱신용
    log = Signal(str, str)         # (레벨, 메시지) — 로그 패널 기록용 (step/info/success/warning/error)
    finished = Signal(str)         # 결과 파일 경로
    error = Signal(str)            # 에러 메시지
    quality_warning = Signal(int, str)   # (페이지번호, 경고메시지)
    ocr_warning = Signal(int, str)       # (페이지번호, 경고메시지)
    # 미리보기 요청: 워커가 GUI 스레드에 미리보기 표시를 요청
    preview_requested = Signal(list)     # list[PageInfo]
    # 크롭 검수 요청: 워커가 GUI 스레드에 크롭 편집 다이얼로그 표시를 요청
    crop_requested = Signal(list)        # list[(PIL.Image, list[CropBox])]

    def __init__(
        self,
        file_path: str,
        output_path: str,
        api_key: str,
        template_path: str | None = None,
        form_path: str | None = None,
        header_values: dict | None = None,
        skip_first_page: bool = False,
        use_crop: bool = False,
        render_figures: bool = False,
        skip_preview: bool = False,
        cache_only: bool = False,
        ocr_backend: str = "auto",
        generate_solutions: bool = False,
    ):
        super().__init__()
        # 정답·해설·메타 자동 생성(2026-08-07) — 세션이 사람 대신 문항을 풀어 OCR JSON 의
        # answer/solution/topic/difficulty 를 채우던 구조를 DeepSeek API 로 옮긴 것.
        self.generate_solutions = bool(generate_solutions)
        self.cache_only = cache_only   # True=저장된 OCR 캐시(merged.json)로 재렌더(크롭·OCR·API 생략)
        self.file_path = file_path
        self.output_path = output_path
        self.api_key = api_key
        # OCR 백엔드(2026-06-16): "auto"(품질기반)·"claude"·"gemini-pro"·"gemini-flash".
        self.ocr_backend = (ocr_backend or "auto").lower()
        self._ocr_engines: dict[str, OCREngine] = {}   # 백엔드별 엔진 lazy 캐시
        self._backend_fallback_warned = False
        self.template_path = template_path
        self.form_path = form_path   # 선택된 대수회 폼(.hwp). 있으면 폼 채움 경로 사용.
        self.header_values = header_values   # 머리말/꼬리말 채움 값(파일명에서 추출).
        self.skip_first_page = skip_first_page
        self.use_crop = use_crop
        self.render_figures = render_figures   # True=그림 렌더(경고 감수), False=안내 박스(경고 없음)
        self.skip_preview = skip_preview       # True=미리보기 생략(OCR 후 바로 변환)
        self._cancelled = False
        # 미리보기 응답 동기화용
        self._preview_event = threading.Event()
        self._preview_approved = False
        # 크롭 편집 응답 동기화용
        self._crop_event = threading.Event()
        self._crop_result: list | None = None   # list[list[CropBox]] | None
        self._crop_approved = False

    def cancel(self):
        self._cancelled = True
        # 대기 중이면 깨우기
        self._preview_event.set()
        self._crop_event.set()

    def set_preview_result(self, approved: bool):
        """GUI 스레드에서 미리보기 결과를 설정."""
        self._preview_approved = approved
        self._preview_event.set()

    def set_crop_result(self, boxes_per_page):
        """GUI 스레드에서 크롭 편집 결과를 설정(None이면 취소)."""
        self._crop_result = boxes_per_page
        self._crop_approved = boxes_per_page is not None
        self._crop_event.set()

    # ── 정답·해설·메타 자동 생성(2026-08-07) ──────────────────────────────────
    def _fill_solutions(self, ocr_result: dict, page_num: int) -> None:
        """OCR 결과(dict)의 문항에 정답·해설·소단원·난이도를 채운다(제자리).

        세션(Claude Code)이 사람 대신 문항을 풀어 채우던 것과 **같은 스키마·같은 소비
        경로**(content_parser → hwp_form_writer._inject_*)이고, 푸는 주체만 DeepSeek API.
        실패해도 변환은 계속한다(정답·해설이 비는 것 = 종전 동작).
        """
        if not self.generate_solutions or self._cancelled:
            return
        qs = [q for q in (ocr_result or {}).get("questions") or [] if isinstance(q, dict)]
        if not qs:
            return
        try:
            from core.solution_generator import generate_solutions as _gen
        except Exception as e:  # noqa: BLE001
            self.log.emit("warning", f"정답·해설 생성 모듈 로드 실패: {e}")
            return
        # ⚠️ header_values 는 form_registry.parse_filename 산출물이라 키가 **한글**이다
        # (학년·과목). 영문 키로 읽으면 항상 빈 문자열이 되어 학년·과목 문맥이 프롬프트에
        # 안 들어간다(적대리뷰 2026-08-07). 영문 키는 폴백으로만 둔다.
        hv = self.header_values or {}
        grade = str(hv.get("학년") or hv.get("grade") or "").strip()
        subject = str(hv.get("과목") or hv.get("subject") or "").strip()
        # 과금이라 시작 시 문항 수와 **예상 비용**을 알린다(실측 문항당 대략 3~6원).
        todo = [q for q in qs if not (q.get("answer") or "").strip()]
        self.log.emit(
            "step",
            f"정답·해설 생성 중 — {page_num}쪽 {len(todo)}문항 (AI 풀이, 예상 "
            f"{len(todo) * 3}~{len(todo) * 6}원)")

        def _prog(done, total, number):
            self.log.emit("info", f"  정답·해설 {done}/{total} (#{number})")

        try:
            st = _gen(qs, grade=grade, subject=subject,
                      progress=_prog, cancel=lambda: self._cancelled)
        except Exception as e:  # noqa: BLE001
            # 키 없음·네트워크 등 — 변환 자체는 계속(정답·해설만 빔).
            self.log.emit("warning", f"정답·해설 생성 실패({page_num}쪽): {e}")
            return
        self.log.emit(
            "info",
            f"  정답·해설 {page_num}쪽: 생성 {st['filled']} / 실패 {st['failed']}"
            + (f" / 건너뜀 {st['skipped']}" if st.get("skipped") else ""))
        # 실패는 **문항 번호까지** 알린다 — 정답만 조용히 빈 채 출하되면 사용자가 알 길이 없다.
        if st.get("failed_numbers"):
            self.log.emit(
                "warning",
                f"  ⚠️ 정답·해설을 만들지 못한 문항: "
                f"{', '.join(str(n) for n in st['failed_numbers'])}번 "
                f"— 해당 문항의 정답·해설란은 비어 있습니다(직접 채워 주세요).")
        u = st.get("usage") or {}
        if u.get("calls"):
            self._log_solution_usage(u)

    def _log_solution_usage(self, u: dict) -> None:
        """DeepSeek 토큰 사용량·비용 로깅 + ``토큰사용.csv`` 누적.

        ⚠️ CSV 기록이 중요하다 — 로그(GUI 패널)는 창을 닫으면 사라져서 **실제 지출 추적이
        안 된다**. OCR(Gemini) 비용만 CSV 에 남고 해설(DeepSeek) 비용은 안 남아, 시험지당
        총비용의 **절반가량이 집계에서 빠져 있었다**(실측 2026-08-07: Gemini 148원만 기록,
        DeepSeek ~90원 누락).
        """
        try:
            model = str(u.get("model") or "")
            # DeepSeek 공식 단가(USD/1M): v4-pro 0.435/0.87, v4-flash 0.14/0.28.
            in_rate, out_rate = (0.14, 0.28) if "flash" in model else (0.435, 0.87)
            inp, out = int(u.get("input_tokens", 0)), int(u.get("output_tokens", 0))
            cr = int(u.get("cached_tokens", 0))
            usd = (inp * in_rate + out * out_rate) / 1e6
            krw = usd * 1500
            self.log.emit(
                "info",
                f"  [USAGE] 해설 {model} 입력 {inp:,} / 출력 {out:,} 토큰 "
                f"= ${usd:.4f} (약 {krw:,.0f}원)")
            _append_usage_csv(self.file_path, model, inp, out, 0, cr,
                              int(u.get("calls", 0)), usd, krw)
        except Exception:  # noqa: BLE001
            pass

    def _ensure_fig_dir(self) -> str:
        """세션 임시 그림 디렉터리를 보장하고 경로 반환."""
        import tempfile
        if not getattr(self, "_fig_dir", None):
            self._fig_dir = tempfile.mkdtemp(prefix="exam_fig_")
        return self._fig_dir

    # ── OCR 백엔드 라우팅(2026-06-16) ──────────────────────────────────────────
    def _resolve_backend_mode(self) -> str:
        """워커가 받은 OCR 백엔드 모드 정규화("auto"|"claude"|"gemini-pro"|"gemini-flash")."""
        b = (self.ocr_backend or "auto").lower()
        return b if b in ("auto", "claude", "gemini-pro", "gemini-flash") else "auto"

    def _get_ocr_engine(self, backend: str) -> OCREngine:
        """백엔드별 엔진을 lazy 생성·캐시.

        ⭐ Claude 폴백 폐지(2026-08-07, 사용자: "claude 는 이제 변환기에서 제외").
        변환기는 Gemini(인식)만 쓴다 — 생성 실패는 키 문제이므로 그대로 올려 중단시킨다.
        """
        eng = self._ocr_engines.get(backend)
        if eng is not None:
            return eng
        eng = OCREngine(backend=backend)      # Gemini 키는 config.json 에서
        self._ocr_engines[backend] = eng
        return eng

    def _page_backend(self, idx: int, page_offset: int,
                      source_kinds, quality_by_index) -> str:
        """문제 페이지 한 장의 OCR 백엔드 결정(자동 모드). 고정 모드면 그 값 그대로.

        자동: born-digital(텍스트레이어/벡터) **또는** 고QC(>=QC_CLEAN_SCORE)면 clean → flash,
        아니면(스캔/저품질=손글씨 가능) pro(충실도 우선·보수적).
        ⚠️ 이 판정은 **크롭 검출로 문제 유무가 확정된 페이지에만** 적용한다(제약 A — 표지·
        답지·빈페이지는 크롭 0개로 이미 제외되어 여기 안 들어옴).
        """
        from utils.config import QC_CLEAN_SCORE
        mode = self._resolve_backend_mode()
        if mode != "auto":
            return mode
        born = False
        if source_kinds:
            si = idx + page_offset
            if 0 <= si < len(source_kinds):
                born = bool(source_kinds[si].get("is_born_digital"))
        q = quality_by_index.get(idx)
        score = float(getattr(q, "score", 0.0)) if q is not None else 0.0
        clean = born or score >= QC_CLEAN_SCORE
        return "gemini-flash" if clean else "gemini-pro"

    def _record_dir(self, kind: str) -> "Path | None":
        """크롭/OCR 기록 **영구 저장** 폴더(``kind`` = 'crop' | 'ocr')/<시험지명>/. 실패 시 None.

        배포 exe 는 크롭·OCR 을 메모리에서만 처리해 실행 후 전부 사라졌다(사용자 2026-06-09:
        "기록으로 봐야겠어"). exe 옆(frozen) 또는 프로젝트 루트(dev)에 ``crop/<시험지>/`` ·
        ``ocr/<시험지>/`` 로 시험지별 남긴다 — 사후 검토·OCR 개선(플라이휠)용.
        """
        try:
            base = (Path(sys.executable).parent if getattr(sys, "frozen", False)
                    else Path(__file__).resolve().parent.parent)
            stem = Path(self.file_path).stem if self.file_path else "unknown"
            d = base / kind / stem
            d.mkdir(parents=True, exist_ok=True)
            return d
        except Exception:
            return None

    def _reset_record_dirs(self) -> None:
        """이번 변환의 크롭/OCR 기록 폴더를 비운다(이전 실행 잔여 파일 혼동 방지). 1회."""
        if getattr(self, "_records_reset", False):
            return
        self._records_reset = True
        for kind in ("crop", "ocr"):
            d = self._record_dir(kind)
            if d is None:
                continue
            for f in d.glob("*"):
                try:
                    if f.is_file():
                        f.unlink()
                except Exception:
                    pass

    def _save_record(self, kind: str, name: str, data) -> None:
        """기록 1건 저장 — kind='crop'(PIL 이미지=PNG) / 'ocr'(dict=JSON). 실패는 무시."""
        d = self._record_dir(kind)
        if d is None:
            return
        try:
            if kind == "crop":
                data.save(str(d / f"{name}.png"))
            else:
                import json as _json
                (d / f"{name}.json").write_text(
                    _json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _render_figure_crop(self, crop, hint, basename):
        """그림 크롭을 재생성(또는 폴백)해 PNG 경로 반환(실패 시 None).

        벡터화 가능·고신뢰 → SVG 재생성 PNG, 그 외 → 원본 크롭 PNG(폴백).
        """
        try:
            png_path, _mode = render_figure(
                crop, hint or "", self._ensure_fig_dir(), basename,
                api_key=self.api_key)
            return png_path
        except Exception as e:  # noqa: BLE001
            logger.warning("그림 재생성 실패: %s", e)
            return None

    def _resolve_figures(self, ocr_dict, source_img, page_num, bi):
        """OCR dict 내 figure 블록을 image 블록으로 해소(재생성/폴백).

        bbox 는 source_img 기준 0~1 정규화. questions 의 contents·choices·
        sub_questions(재귀)를 모두 순회한다. 재생성 실패한 블록은 제거한다.
        """
        counter = [0]

        def _resolve_contents(contents):
            if not isinstance(contents, list):
                return contents
            out = []
            for blk in contents:
                if not (isinstance(blk, dict) and blk.get("type") == "figure"):
                    out.append(blk)
                    continue
                # 그림 렌더링 OFF(체크박스 해제): **SVG 생성 자체를 하지 않고** 안내 텍스트로
                # 대체한다(사용자 2026-06-08: 그림 체크 안 했는데 깨진 SVG 곡선이 보기 박스에
                # 생성됨). 보기/조건 박스 안이든 본문이든 일관 적용 — 깨진 그림 원천 차단.
                if not self.render_figures:
                    out.append({"type": "text", "value": _FIGURE_NOTE_TEXT})
                    continue
                bbox = blk.get("bbox")
                try:
                    if (isinstance(bbox, (list, tuple)) and len(bbox) == 4):
                        x0, y0, x1, y1 = (float(v) for v in bbox)
                        # bbox 는 LLM 추정이라 타이트/저편향 경향 → 여유 pad 로 클리핑 방지
                        # (비전은 주변 텍스트를 무시하고 그림만 재현하므로 넉넉히 잡아도 안전)
                        crop = CropBox(x0, y0, x1, y1).crop_image(source_img, pad=0.05)
                    else:
                        crop = source_img
                except Exception:  # noqa: BLE001
                    crop = source_img
                base = f"fig_p{page_num}_{bi}_{counter[0]}"
                counter[0] += 1
                png = self._render_figure_crop(crop, blk.get("value", ""), base)
                if png:
                    out.append({"type": "image", "value": png})
                # 실패 시 블록 드롭(텍스트 잔재 방지)
            return out

        def _walk_question(q):
            if not isinstance(q, dict):
                return
            if "contents" in q:
                q["contents"] = _resolve_contents(q.get("contents"))
            for ch in q.get("choices", []) or []:
                if isinstance(ch, dict) and "contents" in ch:
                    ch["contents"] = _resolve_contents(ch.get("contents"))
            for sub in q.get("sub_questions", []) or []:
                _walk_question(sub)

        for q in ocr_dict.get("questions", []) or []:
            _walk_question(q)
        return ocr_dict

    def run(self):
        # COM은 스레드별 초기화 필요 — 워커는 QThread 백그라운드에서 돈다.
        # (HWP COM writer + 템플릿 변환 모두 이 스레드에서 COM을 사용한다.)
        try:
            import pythoncom
            pythoncom.CoInitialize()
            _com_init = True
        except Exception:
            _com_init = False
        try:
            self._do_conversion()
        except _FatalApiError as e:
            # 한도 초과·키 무효 — 스택트레이스 대신 **행동 가능한 안내**만 보여 준다.
            logger.warning("변환 중단(복구 불가 API 오류): %s", e)
            self.error.emit(_fatal_api_message(str(e)))
        except Exception as e:
            logger.exception("변환 중 오류 발생")
            self.error.emit(f"변환 실패: {e}\n\n{traceback.format_exc()}")
        finally:
            if _com_init:
                try:
                    import pythoncom
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

    def _do_cache_conversion(self):
        """저장된 OCR 캐시(``ocr/<시험지명>/p{n}_merged.json``)로 **크롭·OCR·API 없이** 재렌더.

        선택한 PDF 파일명(stem)을 기준으로 영구 OCR 기록을 읽어 폼 렌더만 수행한다(API 0원).
        용도: 폼 채움 실패(파일 잠김) 복구, 코드 개선 후 무료 재렌더, 반복 검토. 그림은 안내문구
        (render_figures=False) — 실제 그림 임베드는 크롭 재해소가 필요해 캐시 모드에선 생략.
        """
        self.progress.emit(5, "캐시(OCR 기록) 확인 중...")
        ocr_dir = self._record_dir("ocr")   # ⚠️ _reset_record_dirs 호출 안 함(캐시 보존)
        merged = []
        if ocr_dir is not None:
            merged = sorted(
                ocr_dir.glob("p*_merged.json"),
                key=lambda p: int(re.search(r"p(\d+)_", p.name).group(1)) if re.search(r"p(\d+)_", p.name) else 0)
        if not merged:
            stem = Path(self.file_path).stem if self.file_path else "?"
            self.error.emit(
                f"캐시 없음 — '{stem}' 의 OCR 기록(ocr/<시험지명>/p*_merged.json)이 없습니다.\n"
                "먼저 '변환 시작'으로 한 번 변환하면 기록이 남고, 이후 캐시로 무료 재변환됩니다.")
            return
        self.log.emit("step", f"캐시로 변환 — OCR {len(merged)}페이지 재사용 (크롭·OCR·API 생략)")
        # 완결 마커 검사 — 중간 취소로 남은 부분 캐시면 페이지가 빠진 문서가 나올 수 있다.
        # (마커는 OCR 전 페이지 완료 시에만 기록됨. 구버전 기록엔 없음 → 경고만, 진행은 허용.)
        try:
            marker_fp = ocr_dir / "_complete.json"
            found = {int(re.search(r"p(\d+)_", p.name).group(1)) for p in merged}
            if marker_fp.exists():
                done_pages = set(json.loads(marker_fp.read_text(encoding="utf-8"))
                                 .get("pages", []))
                missing = sorted(done_pages - found)
                if missing:
                    self.log.emit("warning",
                                  f"⚠️ 캐시 페이지 누락 의심 — 기록상 {sorted(done_pages)} 중 "
                                  f"{missing} 페이지의 merged.json 이 없습니다. 결과가 잘릴 수 "
                                  f"있으니 필요하면 '변환 시작'으로 재생성하세요.")
            else:
                self.log.emit("warning",
                              "⚠️ 캐시 완결 마커(_complete.json) 없음 — 중단된 변환의 부분 기록"
                              "이거나 구버전 기록입니다. 페이지 누락 가능성에 유의하세요.")
        except Exception:   # noqa: BLE001 — 마커 검사는 보조 진단, 실패해도 변환 진행
            pass
        pages = []
        for i, fp in enumerate(merged, 1):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
            except Exception as e:   # noqa: BLE001
                self.error.emit(f"캐시 읽기 실패({fp.name}): {e}")
                return
            # 캐시 재렌더에도 정답·해설 생성 적용 — 이미 값이 있는 문항은 generate_solutions
            # 가 건너뛰므로(재시도 보호) 같은 캐시를 다시 돌려도 중복 과금이 없다.
            if self.generate_solutions:
                self._fill_solutions(data, i)
                # 원자적 쓰기 — 도중에 죽어도 사용자의 OCR 기록이 반쪽으로 깨지지 않게.
                try:
                    tmp = fp.with_suffix(fp.suffix + ".tmp")
                    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
                    os.replace(tmp, fp)
                except Exception as e:  # noqa: BLE001
                    self.log.emit("warning", f"캐시 갱신 실패({fp.name}): {e}")
            pages.append(parse_ocr_response(data, page_number=i))
            self.progress.emit(10 + int(i / len(merged) * 60),
                               f"캐시 로드 ({i}/{len(merged)})")

        self.progress.emit(80, "문서 구성 중...")
        self.log.emit("step", "문서 구성 중...")
        document = build_document(pages)
        total_q = sum(len(p.questions) for p in pages)

        self.progress.emit(90, "한글(HWP) 폼지에 채우는 중...")
        if self.form_path and is_hwp_available():
            self.log.emit("step", f"폼지 채움: {Path(self.form_path).name}")
            try:
                result_path = write_exam_to_form(
                    document, self.form_path, self.output_path,
                    header_values=self.header_values, render_figures=False)
            except Exception as e:   # noqa: BLE001
                self.log.emit("warning", f"폼 채움 실패 → 2단 서식으로: {e}")
                result_path = render_plain_2col(document, self.output_path,
                                                info=self.header_values)
        elif is_hwp_available():
            self.log.emit("step", "2단 서식으로 문서 생성 중...")
            result_path = render_plain_2col(document, self.output_path,
                                            info=self.header_values)
        else:
            # HWP 미설치 폴백 — XML 생성기는 .hwpx 만 만든다(.hwp 로 저장하려면 HWP 필요).
            result_path = write_exam_to_hwpx(document,
                                             _as_hwpx_path(self.output_path),
                                             template_path=self.template_path)

        self.progress.emit(100, "변환 완료!")
        self.log.emit("success",
                      f"캐시 변환 완료 — {len(pages)}페이지 · 문항 {total_q} (API 0원)")
        self.finished.emit(str(result_path))

    def _do_conversion(self):
        if self.cache_only:
            self._do_cache_conversion()
            return
        from time import perf_counter
        t_start = perf_counter()
        total_q = 0          # 누적 문항 수
        total_eq = 0         # 누적 수식 수
        total_crops = 0      # 전체 크롭 수(진행바 분모)
        file_path = Path(self.file_path)
        # ⚠️ 기록 폴더 리셋은 여기서 하지 않는다 — 시작 즉시 지우면 크롭 편집 취소/검출 실패
        #    만으로 멀쩡한 기존 캐시('캐시로 변환' 원천)가 사라진다. 새 기록이 실제로 쓰이기
        #    직전(크롭 게이트 통과 후 / OCR 시작 전)에 _reset_record_dirs() 호출(멱등).

        # Step 1: 이미지 로드
        self.progress.emit(5, "파일 로드 중...")
        # born-digital 신호(OCR 백엔드 라우팅용) — PDF 만. 비-PDF(직접 이미지)는 None(스캔 간주).
        source_kinds = page_source_kinds(file_path) if is_pdf(file_path) else None
        if is_pdf(file_path):
            images = pdf_to_images(file_path)
        else:
            images = [load_image(file_path)]

        # 누운(가로) 페이지 자동 보정 (디지털 PDF·정상 이미지는 무변경)
        images = [detect_and_correct_rotation(im) for im in images]

        total_pages = len(images)
        self.progress.emit(10, f"{total_pages}페이지 로드 완료")
        self.log.emit("step", f"{file_path.name} — {total_pages}페이지 로드")

        # ── 표지 건너뛰기 ──
        page_offset = 0
        if self.skip_first_page and total_pages > 1:
            images = images[1:]
            page_offset = 1
            self.progress.emit(10, "첫 페이지(표지) 건너뜀")

        # ── Gate 1: 이미지 품질 검사 ──
        # ⚠️ 페이지 차단 ≠ PDF 차단(제약 B): QC 하드플로어 미달(흐림·저해상도)인 **그 페이지만**
        #    OCR 불가로 건너뛰고 나머지는 계속. 전 페이지 불가일 때만 PDF 거부.
        #    여기 점수(quality)는 뒤 OCR 백엔드 라우팅에서도 재사용(중복 계산 회피).
        self.progress.emit(10, "이미지 품질 검사 중...")
        valid_indices: list[int] = []
        quality_by_index: dict = {}     # images 인덱스 → ImageQuality (라우팅용)

        for i, img in enumerate(images):
            if self._cancelled:
                self.error.emit("사용자에 의해 취소되었습니다.")
                return

            quality = check_image_quality(img)
            quality_by_index[i] = quality
            if not quality.passed:
                warn_msg = (
                    f"페이지 {i + 1} OCR 불가 — 이 페이지만 건너뜁니다(변환은 계속). "
                    f"품질 점수 {quality.score:.0f}: "
                    + "; ".join(quality.warnings)
                )
                self.quality_warning.emit(i + 1, warn_msg)
                logger.warning("건너뛰기 — %s", warn_msg)
            else:
                if quality.warnings:
                    warn_msg = (
                        f"페이지 {i + 1} 경고: "
                        + "; ".join(quality.warnings)
                    )
                    self.quality_warning.emit(i + 1, warn_msg)
                valid_indices.append(i)

        if not valid_indices:
            self.error.emit(
                "변환할 수 있는 페이지가 없습니다 — 모든 페이지가 OCR 불가 품질입니다. "
                "스캔 해상도를 높이거나 더 선명한 원본을 사용하세요.")
            return

        skipped = total_pages - len(valid_indices)
        if skipped > 0:
            self.progress.emit(
                12, f"{skipped}페이지 건너뜀, {len(valid_indices)}페이지 처리 예정"
            )
        self.log.emit(
            "info",
            f"품질 검사 — {len(valid_indices)}페이지 처리"
            + (f" · {skipped}페이지 제외" if skipped else ""),
        )

        # Step 2: OCR 처리
        # 엔진은 페이지별로 _get_ocr_engine(backend) 로 lazy 생성·캐시(라우팅). 단일 고정
        # 엔진을 미리 만들지 않는다 — auto 모드에서 페이지마다 flash/pro 가 갈릴 수 있다.
        mode_label = {"auto": "자동", "claude": "Claude",
                      "gemini-pro": "Gemini Pro", "gemini-flash": "Gemini Flash"}
        self.log.emit("info", f"OCR 엔진: {mode_label.get(self._resolve_backend_mode(), '자동')}")
        pages = []
        page_infos: list[PageInfo] = []
        self._n_skipped_crops = 0   # OCR 인식 실패로 건너뛴 문제영역 수(완료 시 요약·경고)
        self._skipped_numbers: list = []   # 그 문항 번호들(완료 요약에 표시)

        # ── Step 1.5: 크롭 검출 + 사용자 검수 (use_crop 시) ──
        crop_boxes_per_page = None  # valid_indices 와 정렬된 list[list[CropBox]]
        if self.use_crop:
            # 크롭 검출기 표시: Gemini 키 있으면 Gemini(정확), 없으면 Claude 폴백(품질 저하).
            try:
                from utils.config import get_gemini_key
                _gem = bool(get_gemini_key())
            except Exception:
                _gem = False
            self.log.emit(
                "info" if _gem else "warning",
                "크롭 검출: Gemini 사용" if _gem
                else "크롭 검출: Gemini 키 없음 → Claude 폴백(크롭 정확도 낮음). "
                     "Gemini 키를 입력하면 개선됩니다.")
            # ── 크롭 검출을 **페이지 병렬**로 실행(페이지 간 독립 API 콜) — 직렬이던
            #    Gemini 검출이 가장 큰 병목이라 N페이지를 동시에 던져 대폭 단축한다.
            #    결과는 seq(페이지 순서)로 모아 **순서대로** 경고 emit·detected 구성(결정적).
            self.progress.emit(13, f"문제 영역(크롭) 검출 중... (0/{len(valid_indices)})")
            results: dict[int, tuple] = {}     # seq -> (boxes, error)
            n_pages = len(valid_indices)
            cworkers = min(_OCR_WORKERS, max(1, n_pages))
            cex = ThreadPoolExecutor(max_workers=cworkers)
            # Gemini 크롭 실패 → Claude 폴백 시 GUI 에 **1회** 경고(조용한 폴백으로 크롭이
            # 갑자기 이상해진 원인을 못 찾던 문제 방지, 사용자 2026-06-09). 상세는 로그파일.
            self._crop_fallback_warned = False

            def _on_crop_fallback(reason: str) -> None:
                if self._crop_fallback_warned:
                    return
                self._crop_fallback_warned = True
                self.log.emit("warning", f"⚠️ Gemini 크롭 실패 → Claude 폴백(크롭 정확도 저하). "
                                         f"원인: {reason}")
            try:
                futs = {cex.submit(detect_crops, images[idx], self.api_key,
                                   on_fallback=_on_crop_fallback): seq
                        for seq, idx in enumerate(valid_indices)}
                done = 0
                for fut in as_completed(futs):
                    seq = futs[fut]
                    try:
                        results[seq] = (fut.result(), None)
                    except Exception as e:  # noqa: BLE001
                        results[seq] = ([], e)
                    done += 1
                    self.progress.emit(13, f"문제 영역 검출 중... ({done}/{n_pages})")
                    if self._cancelled:
                        break
            finally:
                cex.shutdown(wait=False, cancel_futures=True)
            if self._cancelled:
                self.error.emit("사용자에 의해 취소되었습니다.")
                return

            detected = []
            for seq, idx in enumerate(valid_indices):
                boxes, e = results.get(seq, ([], None))
                if e is not None:
                    logger.warning("크롭 검출 실패(p%d): %s", idx + 1, e)
                    # 실제 원인을 GUI 에 노출 — "검출 실패"만 뜨면 일시적 레이트리밋/크레딧
                    # 부족을 빌드 버그로 오해(2026-06-05). 알려진 원인은 친절히 안내.
                    reason = str(e).strip() or type(e).__name__
                    low = reason.lower()
                    # 한도 초과·키 무효면 여기서 즉시 중단(뒤 페이지도 전부 실패한다).
                    if _is_fatal_api_error(reason):
                        raise _FatalApiError(reason)
                    if any(k in low for k in ("rate", "429", "resource", "exhaust")):
                        reason = "Gemini 레이트리밋 — 잠시 후 다시 시도하세요"
                    # 검출 실패 → 사용자에게 경고(빈 박스로 편집기에 표시, 수동 보강 가능)
                    self.quality_warning.emit(
                        idx + 1 + page_offset,
                        f"페이지 {idx + 1 + page_offset} 문제영역 검출 실패 — {reason[:180]} "
                        f"(편집기에서 직접 추가하거나 빈 채로 두면 건너뜁니다.)")
                if not boxes:
                    # 검출 0개 → 표지/빈 페이지 의심(인식률 낮음 경고). 편집기에서 확인 후
                    # 그대로 두면 자동 스킵된다.
                    self.quality_warning.emit(
                        idx + 1 + page_offset,
                        f"페이지 {idx + 1 + page_offset} 문항 미검출 — 표지/빈 페이지로 "
                        f"보입니다. 비워두면 자동 건너뜁니다.")
                detected.append((images[idx], boxes))

            # 크롭 편집 게이트 (GUI 스레드)
            self._crop_event.clear()
            self._crop_result = None
            self._crop_approved = False
            self.crop_requested.emit(detected)
            self._crop_event.wait()
            if self._cancelled or not self._crop_approved:
                self.error.emit("사용자에 의해 취소되었습니다.")
                return
            crop_boxes_per_page = self._crop_result
            self._reset_record_dirs()   # 게이트 통과 — 이제부터 새 기록으로 갱신(이전 캐시 폐기)

            # ── 무쓸모 페이지 자동 스킵: 편집 후에도 박스 0개인 페이지(표지·빈 페이지·
            #    답안지)는 처리 대상에서 제외 ──
            kept_indices: list[int] = []
            kept_boxes: list[list] = []
            for seq, idx in enumerate(valid_indices):
                page_boxes = crop_boxes_per_page[seq] if crop_boxes_per_page else []
                if page_boxes:
                    kept_indices.append(idx)
                    kept_boxes.append(page_boxes)
                else:
                    self.progress.emit(
                        14, f"페이지 {idx + 1 + page_offset} 건너뜀 (문항 없음)")
                    logger.info("무쓸모 페이지 자동 스킵: p%d", idx + 1 + page_offset)
            if not kept_indices:
                self.error.emit("문항이 검출된 페이지가 없습니다 (모두 표지/빈 페이지).")
                return
            valid_indices = kept_indices
            crop_boxes_per_page = kept_boxes
            self.log.emit(
                "step",
                f"크롭 검출 완료 — {sum(len(b) for b in crop_boxes_per_page)}개 영역")

            # 크롭 박스 좌표(crops.json) + 페이지 오버레이(빨간 박스) 영구 기록 — 크롭 위치
            # 검토용(사용자 2026-06-09). 0~1 정규화 좌표·종류·검출번호 포함.
            try:
                import json as _json
                from PIL import ImageDraw
                cdir = self._record_dir("crop")
                coords = []
                for _seq, _idx in enumerate(valid_indices):
                    _pn = _idx + 1 + page_offset
                    _pb = crop_boxes_per_page[_seq]
                    coords.append({"page": _pn, "boxes": [
                        {"x0": b.x0, "y0": b.y0, "x1": b.x1, "y1": b.y1,
                         "kind": getattr(b, "kind", ""), "number": getattr(b, "number", None)}
                        for b in _pb]})
                    if cdir is not None:
                        try:
                            _ov = images[_idx].convert("RGB").copy()
                            _dr = ImageDraw.Draw(_ov)
                            _W, _H = _ov.size
                            for b in _pb:
                                _dr.rectangle([b.x0 * _W, b.y0 * _H, b.x1 * _W, b.y1 * _H],
                                              outline="red", width=4)
                            _ov.save(str(cdir / f"page{_pn}_boxes.png"))
                        except Exception:
                            pass
                if cdir is not None:
                    (cdir / "crops.json").write_text(
                        _json.dumps(coords, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception as _e:  # noqa: BLE001
                logger.warning("크롭 기록 저장 실패(무시): %s", _e)

        # OCR 인식 시작 — 진행바를 크롭 단위로 부드럽게 움직이기 위해 전체 크롭 수를 분모로.
        self._reset_record_dirs()   # 비크롭 경로 대비(크롭 경로는 게이트 직후 이미 리셋, 멱등)
        if crop_boxes_per_page is not None:
            total_crops = sum(len(b) for b in crop_boxes_per_page)
        crops_done = 0
        self.log.emit(
            "step",
            f"OCR 인식 시작 — {len(valid_indices)}페이지"
            + (f" · {total_crops}크롭" if total_crops else ""))

        for seq, idx in enumerate(valid_indices):
            if self._cancelled:
                self.error.emit("사용자에 의해 취소되었습니다.")
                return

            img = images[idx]
            page_num = idx + 1 + page_offset
            page_t0 = perf_counter()
            pct = 15 + int((seq / len(valid_indices)) * 60)

            # ── OCR 백엔드 라우팅(2026-06-16) — 문제 유무가 확정된 이 페이지에만 적용(제약 A).
            page_backend = self._page_backend(idx, page_offset, source_kinds, quality_by_index)
            eng = self._get_ocr_engine(page_backend)
            if self._resolve_backend_mode() == "auto":
                # 일반 사용자용 안내(모델명·내부용어 대신 쉬운 말).
                self.log.emit(
                    "info",
                    f"페이지 {page_num}: {'빠른 인식' if eng.backend == 'gemini-flash' else '정밀 인식'}")

            if crop_boxes_per_page is not None:
                # 크롭별 개별 OCR → 한 페이지로 병합. figure 크롭은 이미지로 임베딩.
                boxes = crop_boxes_per_page[seq]
                merged = {"header": "", "questions": []}
                pending_figs: list[dict] = []   # 첫 문제 앞에 나온 그림
                last_q: dict | None = None

                # ── ① 문제 박스 OCR 을 병렬 실행(크롭별 독립 API 호출) — 페이지 OCR
                # 시간 대폭 단축. 결과는 아래에서 **박스 순서대로** 병합(순서·pending_figs·
                # last_q 보존). figure 박스 렌더는 순서 의존이라 병합 패스에서 순차 처리.
                def _ocr_box(bi: int, box) -> dict:
                    sub = box.crop_image(img, pad=0.01)
                    self._save_record("crop", f"p{page_num}_c{bi}", sub)   # 크롭 이미지 영구 기록
                    r = eng.recognize_crop(sub)
                    self._save_record("ocr", f"p{page_num}_c{bi}", r)      # OCR 결과 영구 기록
                    self._resolve_figures(r, sub, page_num, bi)  # 문제 내 figure(bbox=sub)
                    return r

                problem_items = [(bi, box) for bi, box in enumerate(boxes)
                                 if box.kind != "figure"]
                self._ensure_fig_dir()   # 병렬 전 메인스레드에서 임시폴더 선생성(레이스 방지)
                ocr_futures: dict = {}
                ex = ThreadPoolExecutor(max_workers=min(_OCR_WORKERS, max(1, len(problem_items))))
                try:
                    if not self._cancelled:
                        ocr_futures = {bi: ex.submit(_ocr_box, bi, box)
                                       for bi, box in problem_items}
                    for bi, box in enumerate(boxes):
                        if self._cancelled:
                            self.error.emit("사용자에 의해 취소되었습니다.")
                            return
                        crops_done += 1
                        self.progress.emit(
                            15 + int(crops_done / max(total_crops, 1) * 60),
                            f"OCR 처리 중... (p{seq + 1} 크롭 {bi + 1}/{len(boxes)})")
                        if box.kind == "figure":
                            # standalone 도형도 체크박스 OFF면 SVG/API 호출 없이 안내문으로 대체.
                            if self.render_figures:
                                crop = box.crop_image(img, pad=0.005)
                                fig_path = self._render_figure_crop(
                                    crop, "", f"fig_p{page_num}_{bi}")
                                block = ({"type": "image", "value": fig_path}
                                         if fig_path else None)
                            else:
                                block = {"type": "text", "value": _FIGURE_NOTE_TEXT}
                            if block:
                                if last_q is not None:
                                    last_q.setdefault("contents", []).append(block)
                                else:
                                    pending_figs.append(block)
                            continue
                        try:
                            r = ocr_futures[bi].result()
                        except Exception as exc:
                            # 크롭 1개의 OCR/JSON 파싱 실패가 전체 변환을 중단시키지
                            # 않도록 격리 — 해당 문항만 건너뛰고 경고 후 계속.
                            logger.warning("크롭 OCR 실패 (p%s 박스 %s): %s",
                                           page_num, bi + 1, exc)
                            # 실제 원인을 GUI 에 노출(프리뷰는 박스만 보여 정상처럼 보이므로
                            # 사용자가 왜 실패했는지 알 수 있게). 잘림(max_tokens)은 명시.
                            reason = str(exc).strip() or type(exc).__name__
                            # ⭐ 사용 한도 초과·키 무효는 **복구 불가** — 남은 페이지를 계속
                            # 돌려도 전부 실패하고 빈 결과만 나온다(실측 2026-08-07: 한도
                            # 초과 후 페이지마다 43초씩 갈아넣고 문항 0개로 완료). 즉시 중단.
                            if _is_fatal_api_error(reason):
                                raise _FatalApiError(reason) from exc
                            if "max_tokens" in reason or "잘렸" in reason or "truncat" in reason.lower():
                                reason = "응답이 max_tokens 로 잘림(수식이 많은 문항). 자동 재시도했으나 실패"
                            self._n_skipped_crops += 1
                            # 어느 문항이 빠졌는지 알아야 사용자가 그 문항만 직접 채운다
                            # (개수만으로는 원본과 대조해야 알 수 있다 — 오성중 실측 2026-08-07).
                            if box.number is not None:
                                self._skipped_numbers.append(box.number)
                            self.quality_warning.emit(
                                page_num,
                                f"페이지 {page_num} {bi + 1}번째 문제영역 인식 실패 — 건너뜀. "
                                f"원인: {reason[:160]}")
                            continue
                        qs = r.get("questions", [])
                        if box.number is not None:
                            for q in qs:
                                q["number"] = box.number  # 검출 번호로 보정
                        if qs and pending_figs:
                            qs[0].setdefault("contents", [])[:0] = pending_figs
                            pending_figs = []
                        merged["questions"].extend(qs)
                        if qs:
                            last_q = qs[-1]
                finally:
                    ex.shutdown(wait=False, cancel_futures=True)
                # 인식률 낮음 경고: 박스는 있었지만 OCR 결과 문항이 0개
                problem_boxes = [b for b in boxes if b.kind != "figure"]
                if problem_boxes and not merged["questions"]:
                    self.quality_warning.emit(
                        page_num,
                        f"페이지 {page_num} 인식률 낮음 — 문제영역 {len(problem_boxes)}개에서 "
                        f"문항을 추출하지 못했습니다. 이미지 품질을 확인하세요.")
                ocr_result = merged
                self._save_record("ocr", f"p{page_num}_merged", merged)  # 페이지 병합 결과 기록
            else:
                self.progress.emit(pct, f"OCR 처리 중... ({seq + 1}/{len(valid_indices)})")
                self._save_record("crop", f"p{page_num}_page", img)    # 페이지 이미지 기록
                ocr_result = eng.recognize_page(img)
                self._save_record("ocr", f"p{page_num}_page", ocr_result)
                # 페이지 내 figure 블록 해소(bbox 는 페이지 이미지 기준)
                self._resolve_figures(ocr_result, img, page_num, 0)

            # ── Gate 2: OCR 응답 검증 ──
            ocr_quality = validate_ocr_response(ocr_result)
            if ocr_quality.warnings:
                warn_msg = (
                    f"페이지 {page_num} OCR 경고: "
                    + "; ".join(ocr_quality.warnings)
                )
                self.ocr_warning.emit(page_num, warn_msg)

            # ── 정답·해설·소단원·난이도 자동 생성(옵션) ──
            # parse **전**에 채워야 content_parser 가 answer/solution 을 블록으로 파싱한다.
            # 채운 뒤 merged 기록을 갱신해 캐시 재렌더에도 정답·해설이 남게 한다.
            if self.generate_solutions:
                self._fill_solutions(ocr_result, page_num)
                if isinstance(ocr_result, dict):
                    self._save_record("ocr", f"p{page_num}_merged", ocr_result)

            page = parse_ocr_response(ocr_result, page_number=page_num)
            pages.append(page)

            # 미리보기용 정보 수집
            img_quality = check_image_quality(img)
            page_infos.append(PageInfo(
                page_number=page_num,
                image=img,
                exam_page=page,
                image_quality=img_quality,
                ocr_quality=ocr_quality,
            ))

            # 페이지 요약(크롭별 8줄 대신 페이지당 1줄로 압축 + 통계)
            total_q += ocr_quality.question_count
            total_eq += ocr_quality.equation_count
            crop_n = len(crop_boxes_per_page[seq]) if crop_boxes_per_page is not None else 0
            self.log.emit(
                "success",
                f"p{page_num} 완료 — "
                + (f"크롭 {crop_n}개 · " if crop_n else "")
                + f"문항 {ocr_quality.question_count} · 수식 {ocr_quality.equation_count} "
                f"({perf_counter() - page_t0:.1f}s)")

        # OCR 전 페이지 완료 — 캐시 완결 마커(중간 취소로 남은 **부분 캐시**를 '캐시로 변환'이
        # 온전한 기록으로 오인해 잘린 문서를 만드는 것 방지). 페이지 목록 포함.
        self._save_record("ocr", "_complete",
                          {"pages": [p.page_number for p in pages]})

        # ── Gate 3: 미리보기 다이얼로그 (GUI 스레드에서 실행) ──
        # skip_preview 면 미리보기를 건너뛰고 곧장 문서 생성으로 진행(사용자 요구 2026-06-05:
        # 미리보기는 확인만 가능해 불필요). 취소만 가능하던 단계라 생략해도 기능 손실 없음.
        if not self.skip_preview:
            self.progress.emit(78, "OCR 완료, 미리보기 준비 중...")
            self._preview_event.clear()
            self._preview_approved = False
            self.preview_requested.emit(page_infos)
            self._preview_event.wait()       # 사용자 응답 대기
            if self._cancelled or not self._preview_approved:
                self.error.emit("사용자에 의해 취소되었습니다.")
                return
        elif self._cancelled:
            self.error.emit("사용자에 의해 취소되었습니다.")
            return

        self.progress.emit(80, "문서 구성 중...")
        self.log.emit("step", "문서 구성 중...")

        # Step 3: 문서 구성
        document = build_document(pages)

        # Step 4: 문서 생성 — 폼 선택 시 폼 채움(대수회), 없으면 COM 기본 렌더,
        # HWP 미설치 시 XML 생성기로 폴백.
        if self.form_path and is_hwp_available():
            self.progress.emit(90, "한글(HWP) 폼지에 채우는 중...")
            self.log.emit("step", f"폼지 채움: {Path(self.form_path).name}")
            try:
                result_path = write_exam_to_form(
                    document, self.form_path, self.output_path,
                    header_values=self.header_values,
                    render_figures=self.render_figures,
                )
            except Exception as e:
                # 폼 채움 실패(구조 불일치 등) → 2단 서식으로 폴백(변환은 산출되게).
                self.log.emit("warning", f"폼 채움 실패 → 2단 서식으로: {e}")
                result_path = render_plain_2col(document, self.output_path,
                                                info=self.header_values)
        elif is_hwp_available():
            # ⭐ 배포 exe 에는 대수회 폼을 넣지 않는다(사용자 2026-08-12) → 여기로 온다.
            # 학교 기출 시험지 양식 2단 바탕(`forms/plain2col`) 위에 본문을 흘려 쓴다.
            # 구현은 웹(커넥터)과 **같은 함수** — 결과가 갈리지 않게.
            self.progress.emit(90, "한글(HWP) 구동하여 문서 생성 중...")
            self.log.emit("step", "2단 서식으로 문서 생성 중...")
            result_path = render_plain_2col(
                document, self.output_path, info=self.header_values
            )
        else:
            self.progress.emit(90, "HWP 미설치 — XML 생성기로 생성 중...")
            self.log.emit("step", "XML 생성기로 문서 생성 중...")
            result_path = write_exam_to_hwpx(
                document, _as_hwpx_path(self.output_path),
                template_path=self.template_path
            )

        self.progress.emit(100, "변환 완료!")
        self.log.emit(
            "success",
            f"변환 완료 — {len(pages)}페이지 · 문항 {total_q} · 수식 {total_eq} · "
            f"총 {perf_counter() - t_start:.1f}s")
        # 인식 실패로 건너뛴 문제영역이 있으면 **눈에 띄게** 알린다 — 일부 문항이 결과에서
        # 빠졌으니 사용자가 원본 화질을 확인·재시도하도록(저화질 스캔 누락 가시화, 2026-06-18).
        if getattr(self, "_n_skipped_crops", 0) > 0:
            nums = sorted(n for n in getattr(self, "_skipped_numbers", []) if n is not None)
            where = f" (원본 {', '.join(str(n) for n in nums)}번)" if nums else ""
            self.log.emit(
                "warning",
                f"⚠ 문제영역 {self._n_skipped_crops}개가 인식 실패로 누락됐습니다{where} — "
                f"해당 문항은 결과에 없으니 직접 채우거나, 더 선명한 스캔으로 다시 시도해 보세요.")
        # 토큰 사용량·예상비용 기록(시험지별, 사용자 2026-06-08 비용계산용). 다중 백엔드면
        # 엔진별(모델별)로 따로 집계 — 폴백으로 같은 객체가 여러 키에 캐시될 수 있어 id 로 dedup.
        try:
            for e in {id(x): x for x in self._ocr_engines.values()}.values():
                msg = _log_token_usage(self.file_path, e.usage, e.model)
                if msg:
                    self.log.emit("info", msg)
        except Exception as e:  # noqa: BLE001
            logger.warning("토큰 사용량 기록 실패(무시): %s", e)
        self.finished.emit(str(result_path))


# ─── 메인 윈도우 ────────────────────────────────────────────

class MainWindow(QMainWindow):
    """수학 시험지 → HWPX 변환 메인 윈도우."""

    def __init__(self):
        super().__init__()
        self._worker: ConversionWorker | None = None
        self._thread: QThread | None = None
        self._typing_warned = False   # 변환 중 타이핑 경고는 세션당 1회만
        self._setup_ui()

    # ── 통일된 크기 상수 ──
    _BTN_HEIGHT = 36
    _PRIMARY_BTN_HEIGHT = 42
    _ICON_SIZE = 16

    def _setup_ui(self):
        try:
            from _version import __version__ as _ver
        except Exception:
            _ver = ""
        self.setWindowTitle(
            f"수학 시험지 한글화 변환기  v{_ver}" if _ver else "수학 시험지 한글화 변환기")
        self.setMinimumSize(720, 600)
        self.setAcceptDrops(True)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(0)
        layout.setContentsMargins(24, 20, 24, 20)

        # ── API 키 입력란은 **제거**(2026-08-07, 사용자) ─────────────────────────
        # 키는 프로그램 폴더의 ``config.json`` 에서 읽는다(배포 시 미리 넣어 둠).
        # 화면에서 입력받지 않으므로 사용자는 파일만 고르면 된다.
        #   · GEMINI_API_KEY   — 문제영역 검출 + OCR(필수)
        #   · DEEPSEEK_API_KEY — 정답·해설 자동 작성(체크박스를 켤 때만)

        # 구분선
        self._add_separator(layout)
        layout.addSpacing(16)

        # ── 섹션 2: 파일 선택 ──
        section_label2 = QLabel("입력 파일")
        section_label2.setStyleSheet(
            "font-size: 11px; font-weight: 600; color: #667085;"
            "text-transform: uppercase; letter-spacing: 1px;"
            "padding: 0; margin: 0;"
        )
        layout.addWidget(section_label2)
        layout.addSpacing(6)

        self._file_path_label = QLabel("파일을 드래그하거나 선택하세요")
        self._file_path_label.setStyleSheet(
            "QLabel {"
            "  border: 2px dashed #d0d5dd;"
            "  border-radius: 10px;"
            "  padding: 24px;"
            "  background: #f9fafb;"
            "  color: #667085;"
            "  font-size: 13px;"
            "}"
        )
        self._file_path_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._file_path_label.setMinimumHeight(80)
        self._file_path_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._file_path_label.mousePressEvent = lambda _: self._browse_file()
        layout.addWidget(self._file_path_label)
        layout.addSpacing(8)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        self._browse_btn = QPushButton("파일 선택")
        self._browse_btn.clicked.connect(self._browse_file)
        self._browse_btn.setFixedHeight(self._BTN_HEIGHT)
        self._browse_btn.setFixedWidth(120)
        btn_layout.addWidget(self._browse_btn)

        out_label = QLabel("출력")
        out_label.setFixedWidth(30)
        out_label.setStyleSheet("font-size: 13px; color: #344054; font-weight: 500;")
        self._output_input = QLineEdit()
        self._output_input.setPlaceholderText("출력 파일 경로 (자동 생성)")
        self._output_input.setFixedHeight(self._BTN_HEIGHT)
        self._output_browse_btn = QPushButton("경로")
        self._output_browse_btn.setFixedHeight(self._BTN_HEIGHT)
        self._output_browse_btn.setFixedWidth(80)
        self._output_browse_btn.setToolTip("출력 경로 직접 지정")
        self._output_browse_btn.clicked.connect(self._browse_output)
        btn_layout.addWidget(out_label)
        btn_layout.addWidget(self._output_input)
        btn_layout.addWidget(self._output_browse_btn)
        layout.addLayout(btn_layout)
        layout.addSpacing(6)

        # ── 처리 방식 안내 (항상 크롭 검수 + 자동 페이지 스킵) ──
        # 크롭 검수는 항상 켜고(2단·도형 정확도↑), 표지/빈 페이지는 문항 미검출로
        # 자동 건너뛴다(수동 '첫 페이지 건너뛰기' 폐지). 인식률 낮은 페이지는 경고.
        info_label = QLabel("✓ 문제 영역 직접 검수(크롭) · 표지·빈 페이지 자동 건너뜀")
        info_label.setStyleSheet("font-size: 12px; color: #027A48;")
        layout.addWidget(info_label)
        layout.addSpacing(6)

        # ── 폼지·OCR 엔진 = **전자동**(2026-08-07, 사용자) ─────────────────────
        # 선택 드롭다운을 없애고 항상 자동으로 처리한다. 실제 동작 차이는 없다 —
        # 두 드롭다운 모두 기본값이 '자동'이었고, 그 자동 로직을 그대로 쓴다:
        #   · 폼지: 파일명(`[학교][학년][과목]…`)에서 학년·과목을 파싱해 폼 매칭.
        #           매칭 실패면 기본 서식으로 렌더(차단하지 않음, 2026-06-16 합의).
        #   · OCR : 페이지 품질로 Gemini Flash(클린·저렴)/Pro(스캔·충실) 자동 분기.
        # 다만 폼 매칭은 **파일명 규칙에 의존**하므로, 감지 결과를 화면에 보여 주고
        # 실패 시 경고한다(예전엔 드롭다운으로 수동 보정이 가능했다).
        self._auto_lbl = QLabel("폼지·인식 방식은 파일을 선택하면 자동으로 정해집니다.")
        self._auto_lbl.setWordWrap(True)
        self._auto_lbl.setStyleSheet("color:#475467; font-size:12px;")
        layout.addWidget(self._auto_lbl)

        # 그림 렌더링 옵션은 폐지(2026-06-16, 사용자) — 그림은 **항상** 안내 박스로 대체한다
        # (render_figures=False 고정). 보안 경고 없이 열리고, 그림은 원본에서 직접 캡처·붙여넣기.

        # 변환 미리보기(OCR 결과 확인) 건너뛰기 — 사용자 요구 2026-06-05(미리보기 단계가
        # 편집 기능이 없어 불필요하다는 의견). 켜면 OCR 후 곧장 문서 생성으로 진행.
        layout.addSpacing(4)
        self._skip_preview_check = QCheckBox("변환 미리보기 건너뛰기 — OCR 후 바로 변환 진행")
        self._skip_preview_check.setChecked(True)   # 기본=건너뜀(미리보기는 확인만 가능)
        self._skip_preview_check.setToolTip(
            "켬(기본): OCR 완료 후 미리보기 없이 곧장 한글 문서를 만든다(빠름).\n"
            "끔: OCR 결과를 미리보기 창에서 확인한 뒤 진행한다.")
        self._skip_preview_check.setStyleSheet(_CHECK_QSS)
        layout.addWidget(self._skip_preview_check)

        # ── 정답·해설 자동 작성(2026-08-07) ────────────────────────────────────
        # AI 가 문항을 직접 풀어 정답면(정답·풀이)과 문항별 [소단원]/[난이도] 메타란을 채운다.
        # 과금이라 기본 OFF. 체크 상태는 config(GENERATE_SOLUTIONS)에 저장해 다음 실행에도 유지.
        layout.addSpacing(4)
        self._gen_sol_check = QCheckBox("정답·해설 자동 작성 — AI가 문제를 풀어 정답면과 단원·난이도를 채웁니다")
        self._gen_sol_check.setToolTip(
            "켬: 문항마다 AI가 직접 풀어서\n"
            "  · 정답면의 정답(①~⑤ 또는 최종답)\n"
            "  · 서술형 풀이(step1, step2 …)\n"
            "  · 문항별 [소단원]·[난이도] 메타란\n"
            "을 채웁니다. 문항 수만큼 시간이 더 걸리고 별도 요금이 발생합니다.\n"
            "끔(기본): 정답·해설란을 비운 채로 변환합니다.")
        self._gen_sol_check.setStyleSheet(_CHECK_QSS)
        try:
            from utils.config import get_generate_solutions
            self._gen_sol_check.setChecked(get_generate_solutions())
        except Exception:
            pass
        self._gen_sol_check.stateChanged.connect(self._on_gen_solutions_changed)
        layout.addWidget(self._gen_sol_check)

        # 구분선
        layout.addSpacing(16)
        self._add_separator(layout)
        layout.addSpacing(16)

        # ── 섹션 3: 변환 ──
        convert_layout = QHBoxLayout()
        convert_layout.setSpacing(10)
        self._convert_btn = QPushButton("변환 시작")
        self._convert_btn.setFixedHeight(self._PRIMARY_BTN_HEIGHT)
        self._convert_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._convert_btn.setStyleSheet(
            "QPushButton {"
            "  background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            "    stop:0 #1570ef, stop:1 #0d6efd);"
            "  color: white;"
            "  border: none;"
            "  border-radius: 8px;"
            "  font-size: 14px;"
            "  font-weight: 600;"
            "  padding: 0 20px;"
            "}"
            "QPushButton:hover {"
            "  background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            "    stop:0 #0d6efd, stop:1 #0b5ed7);"
            "}"
            "QPushButton:pressed { background: #0b5ed7; }"
            "QPushButton:disabled {"
            "  background: #e4e7ec;"
            "  color: #98a2b3;"
            "}"
        )
        self._convert_btn.clicked.connect(self._start_conversion)
        convert_layout.addWidget(self._convert_btn)

        # 캐시로 변환 — 같은 파일명의 저장된 OCR 기록(ocr/<시험지명>/)으로 크롭·OCR·API 없이 재렌더.
        # 폼 채움 실패(파일 잠김) 복구·코드 개선 후 무료 재렌더·반복 검토용(사용자 2026-06-10).
        self._cache_btn = QPushButton("캐시로 변환")
        self._cache_btn.setFixedHeight(self._PRIMARY_BTN_HEIGHT)
        self._cache_btn.setFixedWidth(120)
        self._cache_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cache_btn.setToolTip(
            "선택한 PDF와 같은 파일명의 저장된 OCR 기록으로 크롭·OCR·API 없이 다시 변환합니다.\n"
            "(폼 채움 실패 복구·무료 재렌더용. 먼저 한 번 '변환 시작'으로 변환해야 기록이 생깁니다.)")
        self._cache_btn.setStyleSheet(
            "QPushButton {"
            "  border: 1px solid #b2ddff;"
            "  border-radius: 8px;"
            "  color: #1570ef;"
            "  background: #ffffff;"
            "  font-weight: 600;"
            "}"
            "QPushButton:hover { background: #eff8ff; }"
            "QPushButton:disabled {"
            "  border: 1px solid #e4e7ec;"
            "  color: #98a2b3;"
            "  background: #f2f4f7;"
            "}"
        )
        self._cache_btn.clicked.connect(self._start_cache_conversion)
        convert_layout.addWidget(self._cache_btn)

        self._cancel_btn = QPushButton("취소")
        self._cancel_btn.setFixedHeight(self._PRIMARY_BTN_HEIGHT)
        self._cancel_btn.setFixedWidth(80)
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.setStyleSheet(
            "QPushButton {"
            "  border: 1px solid #fda29b;"
            "  border-radius: 8px;"
            "  color: #b42318;"
            "  background: #ffffff;"
            "  font-weight: 500;"
            "}"
            "QPushButton:hover { background: #fef3f2; }"
            "QPushButton:disabled {"
            "  border: 1px solid #e4e7ec;"
            "  color: #98a2b3;"
            "  background: #f2f4f7;"
            "}"
        )
        self._cancel_btn.clicked.connect(self._cancel_conversion)
        convert_layout.addWidget(self._cancel_btn)
        layout.addLayout(convert_layout)
        layout.addSpacing(12)

        # ── 진행률 ──
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFixedHeight(22)
        layout.addWidget(self._progress_bar)
        layout.addSpacing(4)

        self._status_label = QLabel("대기 중")
        self._status_label.setStyleSheet("color: #667085; font-size: 12px;")
        layout.addWidget(self._status_label)
        layout.addSpacing(12)

        # ── 로그 출력 ──
        log_label = QLabel("변환 로그")
        log_label.setStyleSheet(
            "font-size: 11px; font-weight: 600; color: #667085;"
            "text-transform: uppercase; letter-spacing: 1px;"
            "padding: 0; margin: 0;"
        )
        layout.addWidget(log_label)
        layout.addSpacing(6)

        self._log_output = QPlainTextEdit()
        self._log_output.setReadOnly(True)
        self._log_output.setFont(QFont("Consolas", 9))
        self._log_output.setMaximumBlockCount(500)
        self._log_output.setPlaceholderText("변환 로그가 여기에 표시됩니다...")
        layout.addWidget(self._log_output)

        self._selected_file: str | None = None
        self._selected_template: str | None = None

    @staticmethod
    def _add_separator(layout: QVBoxLayout):
        """얇은 구분선 추가."""
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #e4e7ec;")
        layout.addWidget(sep)

    # 로그 레벨별 (색상, 아이콘, 굵게) — _append_log 가 사용
    _LOG_STYLES = {
        "step":    ("#1570ef", "▸", True),
        "info":    ("#475467", "",  False),
        "success": ("#067647", "✓", False),
        "warning": ("#b54708", "⚠", False),
        "error":   ("#d92d20", "✕", True),
    }

    def _log(self, msg: str):
        """로그 메시지 추가(info 레벨)."""
        self._append_log("info", msg)

    def _on_log(self, level: str, text: str):
        """워커 log 시그널 수신 → 패널에 레벨별 포맷으로 기록."""
        self._append_log(level, text)

    def _append_log(self, level: str, text: str):
        """타임스탬프 + 레벨 색상으로 로그 한 줄을 패널에 추가."""
        import html as _html
        from datetime import datetime
        color, icon, bold = self._LOG_STYLES.get(level, self._LOG_STYLES["info"])
        ts = datetime.now().strftime("%H:%M:%S")
        body = _html.escape(text)
        if bold:
            body = f"<b>{body}</b>"
        prefix = f"{icon} " if icon else ""
        self._log_output.appendHtml(
            f'<span style="color:#98a2b3;">{ts}</span> '
            f'<span style="color:{color};">{prefix}{body}</span>'
        )

    # ── 드래그앤드롭 ──

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls and self._is_supported_file(urls[0].toLocalFile()):
                event.acceptProposedAction()
                self._file_path_label.setStyleSheet(
                    "QLabel {"
                    "  border: 2px dashed #0d6efd;"
                    "  border-radius: 10px;"
                    "  padding: 24px;"
                    "  background: #eff8ff;"
                    "  color: #1570ef;"
                    "  font-size: 13px;"
                    "  font-weight: 500;"
                    "}"
                )

    def dragLeaveEvent(self, event):
        self._reset_drop_style()

    def dropEvent(self, event: QDropEvent):
        self._reset_drop_style()
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            if self._is_supported_file(file_path):
                self._set_file(file_path)

    def _reset_drop_style(self):
        self._file_path_label.setStyleSheet(
            "QLabel {"
            "  border: 2px dashed #d0d5dd;"
            "  border-radius: 10px;"
            "  padding: 24px;"
            "  background: #f9fafb;"
            "  color: #667085;"
            "  font-size: 13px;"
            "}"
        )

    @staticmethod
    def _is_supported_file(path: str) -> bool:
        ext = Path(path).suffix.lower()
        return ext in get_supported_extensions()

    def _set_file(self, path: str):
        self._selected_file = path
        name = Path(path).name
        self._file_path_label.setText(name)
        self._file_path_label.setStyleSheet(
            "QLabel {"
            "  border: 2px solid #32d583;"
            "  border-radius: 10px;"
            "  padding: 24px;"
            "  background: #ecfdf3;"
            "  color: #027a48;"
            "  font-size: 13px;"
            "  font-weight: 600;"
            "}"
        )

        # 출력 경로 자동 설정
        # 출력은 .hwp — .hwpx 로는 폼 바탕쪽(2단 가운데 구분선)이 적용되지 않는다
        # (core.hwp_com.save_as_hwp 주석, 2026-07-24). 중간 후처리만 .hwpx.
        out_name = Path(path).stem + "_변환.hwp"
        out_path = get_output_dir() / out_name
        self._output_input.setText(str(out_path))
        self._log(f"파일 선택: {path}")
        # 폼은 항상 자동 매칭 — 파일명에서 감지한 결과를 화면에 보여 준다(드롭다운 폐지
        # 2026-08-07 이후로는 이 안내가 유일한 확인 수단이라 상단 라벨에도 함께 띄운다).
        if True:
            info = parse_filename(path)
            if info["valid"]:
                fp = resolve_form(path)
                self._log(
                    f"  파일명 인식: {info['학년']} {info['과목']} · "
                    f"{info['년도']}년 {info['학기']}학기 {info['구분']}")
                self._log(f"  자동 폼: {Path(fp).name if fp else '미매칭 → 기본 서식'}")
                self._set_auto_label(
                    f"폼지: {Path(fp).stem if fp else '기본 서식(폼 미매칭)'} · 인식: 빠른 인식(Gemini Flash)")
            else:
                # valid=False 라도 학교/학년/시기는 보통 인식된다(과목 미인식이 대부분 원인) —
                # 무엇이 읽혔고 무엇이 빠졌는지 구체적으로 알려 준다(2026-06-18).
                got = []
                if info["학년"]:
                    got.append(info["학년"])
                if info["년도"]:
                    got.append(f"{info['년도']}년 {info['학기']}학기 {info['구분']}")
                if got:
                    self._log(f"  파일명 인식: {' · '.join(got)} (과목 미인식)")
                    self._log(
                        "  ⚠ 과목을 못 읽어 폼 자동 채움 불가 → 기본 서식으로 변환합니다.")
                else:
                    self._log("  ⚠ 파일명에서 학교/학년을 못 읽어 폼 자동 채움 불가.")
                self._log(
                    "  형식: [학교][학년][과목][년-학기-중간/기말]([출판사]) · "
                    "과목 예: 대수 · 미적1(수2) · 확통 · 미적분 · 기하 · 공수1 · 공수2")
                self._set_auto_label(
                    "폼지: 기본 서식(파일명 규칙 미일치) · 인식: 빠른 인식(Gemini Flash)",
                    warn=True)

    def _set_auto_label(self, text: str, warn: bool = False) -> None:
        """상단 자동 설정 안내 라벨 갱신(폼 미매칭이면 주황색 경고)."""
        try:
            self._auto_lbl.setText(text)
            self._auto_lbl.setStyleSheet(
                "color:#b54708; font-size:12px;" if warn else "color:#475467; font-size:12px;")
        except Exception:  # noqa: BLE001
            pass

    # ── 파일 선택 ──

    def _browse_file(self):
        exts = " ".join(f"*{e}" for e in sorted(get_supported_extensions()))
        path, _ = QFileDialog.getOpenFileName(
            self,
            "시험지 파일 선택",
            "",
            f"지원 파일 ({exts});;모든 파일 (*.*)",
        )
        if path:
            self._set_file(path)

    def _browse_output(self):
        """출력 경로 직접 지정."""
        current = self._output_input.text().strip()
        start_dir = str(Path(current).parent) if current else ""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "출력 파일 경로 지정",
            current or start_dir,
            "한글 파일 (*.hwp);;HWPX 파일 (*.hwpx);;모든 파일 (*.*)",
        )
        if path:
            self._output_input.setText(path)
            self._log(f"출력 경로 지정: {path}")

    # 폼지 선택·OCR 엔진 선택 핸들러는 제거(2026-08-07) — 둘 다 전자동.

    def _on_gen_solutions_changed(self, _state: int):
        """정답·해설 자동 작성 체크 → config(GENERATE_SOLUTIONS) 저장 + 키 확인 안내."""
        on = self._gen_sol_check.isChecked()
        try:
            from utils.config import _load_config, save_config, _init_module_vars
            cfg = _load_config()
            cfg["GENERATE_SOLUTIONS"] = on
            save_config(cfg)
            _init_module_vars()
        except Exception as e:  # noqa: BLE001
            logger.warning("정답·해설 설정 저장 실패(무시): %s", e)
        if on:
            try:
                from utils.config import get_deepseek_key
                if not get_deepseek_key():
                    QMessageBox.warning(
                        self, "API 키 필요",
                        "정답·해설 자동 작성에는 DeepSeek API 키가 필요합니다.\n"
                        "config.json 의 \"DEEPSEEK_API_KEY\" 에 키를 넣어 주세요.\n\n"
                        "키가 없으면 정답·해설란은 비어 있는 상태로 변환됩니다.")
            except Exception:  # noqa: BLE001
                pass
        self._log("정답·해설 자동 작성: " + ("켬" if on else "끔"))

    def _resolve_form_path(self) -> str | None:
        """입력 파일명 → 폼 경로(매칭 실패면 None=기본 서식).

        드롭다운 폐지(2026-08-07)로 **항상 자동 매칭**이다. 파일명 규칙
        (`[학교][학년][과목][년-학기-중간/기말]`)에서 학년·과목을 읽어 폼을 고른다.
        """
        return resolve_form(self._selected_file or "")

    # ── 변환 ──

    def _start_conversion(self):
        if not self._selected_file:
            QMessageBox.warning(self, "알림", "변환할 파일을 선택하세요.")
            return

        # 키는 화면에서 입력받지 않고 ``config.json`` 에서 읽는다(2026-08-07, 사용자).
        # OCR 은 Gemini Flash 고정이므로 Gemini 키만 필수다.
        from utils.config import get_api_key, get_gemini_key
        try:
            api_key = get_api_key()
        except Exception:  # noqa: BLE001 — 키 없음도 정상(Gemini 만 쓰므로)
            api_key = ""
        gemini_key = get_gemini_key()
        ocr_backend = _FIXED_OCR_BACKEND
        if not gemini_key:
            QMessageBox.warning(
                self, "API 키 없음",
                "Gemini API 키가 설정돼 있지 않습니다.\n\n"
                "프로그램 폴더의 config.json 을 열어 \"GEMINI_API_KEY\" 에 키를 넣어 주세요.")
            return

        # 폼은 파일명(`[학교][학년][과목]…`)으로 자동 매칭한다. 규칙과 안 맞으면 **차단하지 않고**
        # 기본 서식(폼 없음)으로 렌더한다(스타일 동일, 사용자 2026-06-16).
        info = parse_filename(self._selected_file)
        if not info["valid"]:
            self._log("폼 자동: 파일명 규칙 미일치 → 기본 서식(폼 없음)으로 변환합니다.")

        output_path = self._output_input.text().strip()
        if not output_path:
            QMessageBox.warning(self, "알림", "출력 경로를 지정하세요.")
            return

        # 출력 파일이 이미 있으면 윈도우처럼 " (1)"·" (2)"… 를 붙여 새 파일로(덮어쓰기 안 함,
        # 사용자 2026-06-09). 기존 변환물 보존 + 재변환 비교 편의.
        if Path(output_path).exists():
            new_path = _unique_output_path(output_path)
            self._log(f"기존 파일 있음 → 새 이름으로 저장: {Path(new_path).name}")
            output_path = new_path
            self._output_input.setText(output_path)

        # 출력 디렉토리 생성
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # 변환 중 타이핑 경고(세션당 1회) — 실시간 작성 표시가 켜져 있으면 한글 창이
        # 떠 포커스를 받을 수 있어, 다른 데서 친 키가 본문에 섞인다(사용자 보고).
        from core.hwp_com import CONVERSION_VISIBLE
        if CONVERSION_VISIBLE and not self._typing_warned:
            QMessageBox.warning(
                self, "변환 중 타이핑 주의",
                "변환이 진행되는 동안 한글(HWP) 창이 떠서 실시간으로 작성됩니다.\n\n"
                "이때 다른 창에서 타이핑하면 그 글자가 한글 본문에 섞여 들어갈 수 있습니다.\n"
                "변환이 끝날 때까지 키보드 입력을 멈춰 주세요.\n\n"
                "(이 안내는 이번 실행에서 한 번만 표시됩니다.)",
            )
            self._typing_warned = True

        self._set_ui_converting(True)
        self._progress_bar.setValue(0)
        self._log("=" * 40)
        self._log("변환 시작...")

        # 워커 스레드 생성
        worker = ConversionWorker(
            self._selected_file, output_path, api_key,
            template_path=self._selected_template,
            form_path=self._resolve_form_path(),   # 폼 선택(자동/수동) → 경로 or None
            header_values=(info if info["valid"] else None),  # 머리말 채움 값(파일명)
            skip_first_page=False,   # 수동 표지 스킵 폐지 — 무쓸모 페이지는 자동 스킵
            use_crop=True,           # 항상 크롭 검수 모드
            render_figures=False,    # 그림 렌더 폐지(항상 안내 박스, 2026-06-16)
            skip_preview=self._skip_preview_check.isChecked(),  # 미리보기 생략 여부
            ocr_backend=_FIXED_OCR_BACKEND,     # 인식 엔진 고정(2026-08-07)
            generate_solutions=self._gen_sol_check.isChecked(),    # 정답·해설 자동 작성
        )
        self._run_worker(worker)

    def _run_worker(self, worker: "ConversionWorker") -> None:
        """워커를 스레드에 올리고 시그널을 연결해 시작(일반·캐시 변환 공통)."""
        self._thread = QThread()
        self._worker = worker
        worker.moveToThread(self._thread)
        self._thread.started.connect(worker.run)
        worker.progress.connect(self._on_progress)
        worker.log.connect(self._on_log)
        worker.finished.connect(self._on_finished)
        worker.error.connect(self._on_error)
        worker.quality_warning.connect(self._on_quality_warning)
        worker.ocr_warning.connect(self._on_ocr_warning)
        worker.preview_requested.connect(self._on_preview_requested)
        worker.crop_requested.connect(self._on_crop_requested)
        worker.finished.connect(self._thread.quit)
        worker.error.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)
        self._thread.start()

    def _cache_dir_for_selected(self) -> "Path | None":
        """선택한 PDF 파일명(stem) 기준 OCR 캐시 폴더(``ocr/<시험지명>/``). 없으면 None."""
        if not self._selected_file:
            return None
        base = (Path(sys.executable).parent if getattr(sys, "frozen", False)
                else Path(__file__).resolve().parent.parent)
        d = base / "ocr" / Path(self._selected_file).stem
        return d if d.exists() else None

    def _start_cache_conversion(self):
        """캐시로 변환 — 선택한 PDF와 **같은 파일명**의 OCR 기록으로 크롭·OCR·API 없이 재렌더."""
        if not self._selected_file:
            QMessageBox.warning(self, "알림", "변환할 파일을 선택하세요 (캐시는 파일명 기준).")
            return
        cache_dir = self._cache_dir_for_selected()
        merged = sorted(cache_dir.glob("p*_merged.json")) if cache_dir else []
        if not merged:
            stem = Path(self._selected_file).stem
            QMessageBox.warning(
                self, "캐시 없음",
                f"'{stem}' 의 OCR 캐시가 없습니다.\n\n"
                "먼저 '변환 시작'으로 한 번 변환하면 ocr/<시험지명>/ 에 기록이 남고,\n"
                "이후 이 버튼으로 OCR 비용 없이 다시 변환할 수 있습니다.")
            return

        info = parse_filename(self._selected_file)
        output_path = self._output_input.text().strip()
        if not output_path:
            QMessageBox.warning(self, "알림", "출력 경로를 지정하세요.")
            return
        # 출력 파일이 이미 있으면(열려 있어 잠겼을 수 있음) 새 이름으로 → 잠김(WinError 5) 회피.
        if Path(output_path).exists():
            output_path = _unique_output_path(output_path)
            self._log(f"기존 파일 있음 → 새 이름으로 저장: {Path(output_path).name}")
            self._output_input.setText(output_path)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        self._set_ui_converting(True)
        self._progress_bar.setValue(0)
        self._log("=" * 40)
        self._log(f"캐시로 변환 시작 — OCR {len(merged)}페이지 재사용 (API 0원)...")

        worker = ConversionWorker(
            self._selected_file, output_path, api_key="",
            template_path=self._selected_template,
            form_path=self._resolve_form_path(),
            header_values=(info if info["valid"] else None),
            cache_only=True,
            generate_solutions=self._gen_sol_check.isChecked(),    # 정답·해설 자동 작성
        )
        self._run_worker(worker)

    def _cancel_conversion(self):
        if self._worker:
            self._worker.cancel()
            self._log("취소 요청됨...")

    def _on_progress(self, percent: int, message: str):
        # 진행바·상태라벨만 실시간 갱신(크롭마다). 로그 기록은 log 시그널로 분리.
        self._progress_bar.setValue(percent)
        self._status_label.setText(message)

    def _on_finished(self, result_path: str):
        self._set_ui_converting(False)
        self._append_log("success", f"저장됨: {result_path}")
        self._status_label.setText("변환 완료!")

        QMessageBox.information(
            self,
            "변환 완료",
            f"HWPX 파일이 생성되었습니다.\n\n{result_path}",
        )

    def _on_error(self, error_msg: str):
        self._set_ui_converting(False)
        self._append_log("error", error_msg)
        self._status_label.setText("오류 발생")
        self._progress_bar.setValue(0)

        QMessageBox.critical(self, "변환 오류", error_msg)

    def _cleanup_thread(self):
        self._thread = None
        self._worker = None

    def _on_quality_warning(self, page_num: int, message: str):
        self._append_log("warning", message)

    def _on_ocr_warning(self, page_num: int, message: str):
        self._append_log("warning", message)

    def _on_preview_requested(self, page_infos: list):
        """워커에서 미리보기 요청 → GUI 스레드에서 다이얼로그 표시."""
        dialog = PreviewDialog(page_infos, parent=self)
        result = dialog.exec()
        approved = result == PreviewDialog.DialogCode.Accepted
        if self._worker:
            self._worker.set_preview_result(approved)

    def _on_crop_requested(self, pages: list):
        """워커에서 크롭 검수 요청 → GUI 스레드에서 편집 다이얼로그 표시.

        pages: list[(PIL.Image, list[CropBox])]. 확정 시 페이지별 박스 리스트 반환,
        취소 시 None.
        """
        from gui.crop_editor_dialog import CropEditorDialog
        dialog = CropEditorDialog(list(pages), parent=self)
        result = dialog.exec()
        boxes = dialog.result_boxes if result == CropEditorDialog.DialogCode.Accepted else None
        if self._worker:
            self._worker.set_crop_result(boxes)

    def closeEvent(self, event):
        """변환 중 창 닫기 방어 — 워커 미정리로 QThread 파괴 크래시/이벤트 영구대기 방지."""
        if self._thread is not None and self._thread.isRunning():
            ret = QMessageBox.question(
                self, "종료 확인",
                "변환이 진행 중입니다. 중단하고 종료할까요?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if ret != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            if self._worker:
                self._worker.cancel()          # _cancelled + 크롭/프리뷰 이벤트 set(대기 해제)
            self._thread.quit()
            if not self._thread.wait(5000):    # 정상 종료 대기(취소 체크포인트 도달까지)
                self._thread.terminate()       # COM 행 등 최후수단 — 앱 종료 직전이라 허용
                self._thread.wait(2000)
        event.accept()

    def _set_ui_converting(self, converting: bool):
        self._convert_btn.setEnabled(not converting)
        self._cache_btn.setEnabled(not converting)
        self._cancel_btn.setEnabled(converting)
        self._browse_btn.setEnabled(not converting)
        self._output_browse_btn.setEnabled(not converting)
        # 키 입력란·폼지/OCR 드롭다운은 제거됨(2026-08-07) — 비활성화 대상 없음.
        self._skip_preview_check.setEnabled(not converting)
