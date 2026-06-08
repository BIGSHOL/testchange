"""PySide6 메인 윈도우 모듈.

드래그앤드롭, 파일 선택, 변환 진행률, 설정 관리를 포함합니다.
"""

from __future__ import annotations

import logging
import sys
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QThread, QObject
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
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
    pdf_to_images,
)
from core.ocr_engine import OCREngine, validate_ocr_response
from core.crop_detector import detect_crops, CropBox
from core.figure_generator import render_figure
from core.quality_checker import check_image_quality
from core.content_parser import parse_ocr_response, build_document
from core.hwpx_writer import write_exam_to_hwpx
from core.hwp_com import is_hwp_available
from core.hwp_com_writer import write_exam_to_hwp
from core.hwp_form_writer import write_exam_to_form
from core.form_registry import list_forms, resolve_auto, resolve_form, parse_filename
from gui.preview_dialog import PreviewDialog, PageInfo
from utils.config import get_output_dir

logger = logging.getLogger(__name__)

# 크롭 OCR 병렬 처리 동시 실행 수(①). 너무 크면 API 레이트리밋, 작으면 속도 이득 적음.
_OCR_WORKERS = 6


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
    ):
        super().__init__()
        self.file_path = file_path
        self.output_path = output_path
        self.api_key = api_key
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

    def _ensure_fig_dir(self) -> str:
        """세션 임시 그림 디렉터리를 보장하고 경로 반환."""
        import tempfile
        if not getattr(self, "_fig_dir", None):
            self._fig_dir = tempfile.mkdtemp(prefix="exam_fig_")
        return self._fig_dir

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

    def _do_conversion(self):
        from time import perf_counter
        t_start = perf_counter()
        total_q = 0          # 누적 문항 수
        total_eq = 0         # 누적 수식 수
        total_crops = 0      # 전체 크롭 수(진행바 분모)
        file_path = Path(self.file_path)

        # Step 1: 이미지 로드
        self.progress.emit(5, "파일 로드 중...")
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
        self.progress.emit(10, "이미지 품질 검사 중...")
        valid_indices: list[int] = []

        for i, img in enumerate(images):
            if self._cancelled:
                self.error.emit("사용자에 의해 취소되었습니다.")
                return

            quality = check_image_quality(img)
            if not quality.passed:
                warn_msg = (
                    f"페이지 {i + 1} 품질 불합격 (점수 {quality.score:.0f}): "
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
            self.error.emit("모든 페이지가 품질 검사에 불합격했습니다.")
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
        engine = OCREngine(api_key=self.api_key)
        pages = []
        page_infos: list[PageInfo] = []

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
            self.progress.emit(13, "문제 영역(크롭) 검출 중...")
            detected = []
            for seq, idx in enumerate(valid_indices):
                if self._cancelled:
                    self.error.emit("사용자에 의해 취소되었습니다.")
                    return
                self.progress.emit(13, f"문제 영역 검출 중... ({seq + 1}/{len(valid_indices)})")
                try:
                    boxes = detect_crops(images[idx], api_key=self.api_key)
                except Exception as e:
                    logger.warning("크롭 검출 실패(p%d): %s", idx + 1, e)
                    # 실제 원인을 GUI 에 노출 — "검출 실패"만 뜨면 일시적 레이트리밋/크레딧
                    # 부족을 빌드 버그로 오해(2026-06-05). 알려진 원인은 친절히 안내.
                    reason = str(e).strip() or type(e).__name__
                    low = reason.lower()
                    if "credit" in low or "balance" in low:
                        reason = "Anthropic 크레딧 부족 — 크레딧 충전 필요(폼/OCR 도 동일)"
                    elif any(k in low for k in ("rate", "429", "quota", "resource", "exhaust")):
                        reason = "Gemini 레이트리밋/쿼터 초과 — 잠시 후 다시 시도하세요"
                    # 검출 실패 → 사용자에게 경고(빈 박스로 편집기에 표시, 수동 보강 가능)
                    self.quality_warning.emit(
                        idx + 1 + page_offset,
                        f"페이지 {idx + 1 + page_offset} 문제영역 검출 실패 — {reason[:180]} "
                        f"(편집기에서 직접 추가하거나 빈 채로 두면 건너뜁니다.)")
                    boxes = []
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

        # OCR 인식 시작 — 진행바를 크롭 단위로 부드럽게 움직이기 위해 전체 크롭 수를 분모로.
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
                    r = engine.recognize_crop(sub)
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
                            # standalone 도형 → 재생성(또는 크롭 폴백) 후 IMAGE 블록 생성
                            crop = box.crop_image(img, pad=0.005)
                            fig_path = self._render_figure_crop(
                                crop, "", f"fig_p{page_num}_{bi}")
                            if fig_path:
                                block = {"type": "image", "value": fig_path}
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
                            if "max_tokens" in reason or "잘렸" in reason or "truncat" in reason.lower():
                                reason = "응답이 max_tokens 로 잘림(수식이 많은 문항). 자동 재시도했으나 실패"
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
            else:
                self.progress.emit(pct, f"OCR 처리 중... ({seq + 1}/{len(valid_indices)})")
                ocr_result = engine.recognize_page(img)
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
                # 폼 채움 실패(구조 불일치 등) → 기본 서식으로 폴백(변환은 산출되게).
                self.log.emit("warning", f"폼 채움 실패 → 기본 서식으로: {e}")
                result_path = write_exam_to_hwp(document, self.output_path)
        elif is_hwp_available():
            self.progress.emit(90, "한글(HWP) 구동하여 문서 생성 중...")
            self.log.emit("step", "한글(HWP) 문서 생성 중...")
            result_path = write_exam_to_hwp(
                document, self.output_path, template_path=self.template_path
            )
        else:
            self.progress.emit(90, "HWP 미설치 — XML 생성기로 생성 중...")
            self.log.emit("step", "XML 생성기로 문서 생성 중...")
            result_path = write_exam_to_hwpx(
                document, self.output_path, template_path=self.template_path
            )

        self.progress.emit(100, "변환 완료!")
        self.log.emit(
            "success",
            f"변환 완료 — {len(pages)}페이지 · 문항 {total_q} · 수식 {total_eq} · "
            f"총 {perf_counter() - t_start:.1f}s")
        self.finished.emit(str(result_path))


# ─── 메인 윈도우 ────────────────────────────────────────────

class MainWindow(QMainWindow):
    """수학 시험지 → HWPX 변환 메인 윈도우."""

    def __init__(self):
        super().__init__()
        self._worker: ConversionWorker | None = None
        self._thread: QThread | None = None
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

        # ── 섹션 1: API 키 ──
        section_label = QLabel("API 설정")
        section_label.setStyleSheet(
            "font-size: 11px; font-weight: 600; color: #667085;"
            "text-transform: uppercase; letter-spacing: 1px;"
            "padding: 0; margin: 0;"
        )
        layout.addWidget(section_label)
        layout.addSpacing(6)

        api_layout = QHBoxLayout()
        api_layout.setSpacing(10)
        api_label = QLabel("API 키")
        api_label.setFixedWidth(48)
        api_label.setStyleSheet("font-size: 13px; color: #344054; font-weight: 500;")
        self._api_key_input = QLineEdit()
        self._api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_input.setPlaceholderText("Anthropic API 키를 입력하세요")
        self._api_key_input.setFixedHeight(self._BTN_HEIGHT)
        self._load_api_key()
        api_layout.addWidget(api_label)
        api_layout.addWidget(self._api_key_input)
        layout.addLayout(api_layout)

        # Gemini 키(크롭 검출 정확도 — 없으면 Claude 폴백, 크롭 품질 저하)
        layout.addSpacing(8)
        gem_layout = QHBoxLayout()
        gem_layout.setSpacing(10)
        gem_label = QLabel("Gemini")
        gem_label.setFixedWidth(48)
        gem_label.setStyleSheet("font-size: 13px; color: #344054; font-weight: 500;")
        self._gemini_key_input = QLineEdit()
        self._gemini_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._gemini_key_input.setPlaceholderText("Gemini API 키 (문제영역 크롭 검출용 — 권장)")
        self._gemini_key_input.setFixedHeight(self._BTN_HEIGHT)
        self._load_gemini_key()
        gem_layout.addWidget(gem_label)
        gem_layout.addWidget(self._gemini_key_input)
        layout.addLayout(gem_layout)

        # 구분선
        layout.addSpacing(16)
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

        # ── 폼지(양식) 선택 ──
        # '자동'은 입력 파일명의 학년(예: [조암중][2] → 중2)을 감지해 맞는 폼을 고른다.
        # 구체 폼을 직접 고르면 그 폼으로, '기본 서식'이면 폼 없이 표준 렌더.
        form_layout = QHBoxLayout()
        form_layout.setSpacing(10)
        form_lbl = QLabel("폼지")
        form_lbl.setFixedWidth(120)
        form_layout.addWidget(form_lbl)

        self._form_combo = QComboBox()
        self._form_combo.setFixedHeight(self._BTN_HEIGHT)
        self._form_combo.setToolTip(
            "대수회 폼지에 채워 출력합니다.\n"
            "· 자동: 파일명의 학년을 감지해 맞는 폼 선택\n"
            "· 기본 서식: 폼 없이 표준 서식으로 생성"
        )
        self._form_combo.addItem("자동 (학년 감지)", "__AUTO__")
        self._form_combo.addItem("기본 서식 (폼 없음)", "__NONE__")
        for fi in list_forms():
            self._form_combo.addItem(f"폼지 — {fi.display}", fi.path)
        self._form_combo.addItem("직접 찾아보기…", "__BROWSE__")
        self._form_combo.currentIndexChanged.connect(self._on_form_changed)
        form_layout.addWidget(self._form_combo, 1)
        layout.addLayout(form_layout)

        # 그림(문제 내 도형/그래프) 처리 모드 선택
        layout.addSpacing(8)
        self._render_fig_check = QCheckBox("그림 렌더링(도형/그래프 삽입) — 끄면 그림 자리에 안내 박스")
        self._render_fig_check.setChecked(False)   # 기본=끔(보안 경고 없음). 켜면 그림 보이나 경고.
        self._render_fig_check.setToolTip(
            "끔(기본): 그림을 넣지 않고 '직접 캡처해 붙여넣으세요' 안내 박스를 둔다 — "
            "문서가 보안 경고 없이 열린다.\n"
            "켬: 도형/그래프를 실제로 삽입한다 — 단 한글에서 열 때 '문서 보안 설정' 경고가 뜰 수 있다.")
        self._render_fig_check.setStyleSheet("font-size: 12px; color: #475467;")
        layout.addWidget(self._render_fig_check)

        # 변환 미리보기(OCR 결과 확인) 건너뛰기 — 사용자 요구 2026-06-05(미리보기 단계가
        # 편집 기능이 없어 불필요하다는 의견). 켜면 OCR 후 곧장 문서 생성으로 진행.
        layout.addSpacing(4)
        self._skip_preview_check = QCheckBox("변환 미리보기 건너뛰기 — OCR 후 바로 변환 진행")
        self._skip_preview_check.setChecked(True)   # 기본=건너뜀(미리보기는 확인만 가능)
        self._skip_preview_check.setToolTip(
            "켬(기본): OCR 완료 후 미리보기 없이 곧장 한글 문서를 만든다(빠름).\n"
            "끔: OCR 결과를 미리보기 창에서 확인한 뒤 진행한다.")
        self._skip_preview_check.setStyleSheet("font-size: 12px; color: #475467;")
        layout.addWidget(self._skip_preview_check)

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

    def _load_api_key(self):
        """설정에서 API 키 로드."""
        try:
            from utils.config import get_api_key
            key = get_api_key()
            self._api_key_input.setText(key)
        except ValueError:
            pass

    def _load_gemini_key(self):
        """설정에서 Gemini 키 로드(없으면 빈칸)."""
        try:
            from utils.config import get_gemini_key
            self._gemini_key_input.setText(get_gemini_key())
        except Exception:
            pass

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
        out_name = Path(path).stem + "_변환.hwpx"
        out_path = get_output_dir() / out_name
        self._output_input.setText(str(out_path))
        self._log(f"파일 선택: {path}")
        # 폼 '자동'이면 파일명 규칙 검사·감지 결과 안내(드롭다운은 '자동' 유지).
        if self._form_combo.currentData() == "__AUTO__":
            info = parse_filename(path)
            if info["valid"]:
                fp = resolve_form(path)
                self._log(
                    f"  파일명 인식: {info['학년']} {info['과목']} · "
                    f"{info['년도']}년 {info['학기']}학기 {info['구분']}")
                self._log(f"  자동 폼: {Path(fp).name if fp else '미매칭(드롭다운에서 선택)'}")
            else:
                self._log(
                    "  ⚠ 파일명이 규칙과 다릅니다 → 폼 자동 채움 불가. "
                    "형식: [학교][학년][년-학기-중간/기말]([과목]) — 끝의 [출판사]는 선택")

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
            "HWPX 파일 (*.hwpx);;모든 파일 (*.*)",
        )
        if path:
            self._output_input.setText(path)
            self._log(f"출력 경로 지정: {path}")

    # ── 폼지(양식) 선택 ──

    def _on_form_changed(self, idx: int):
        """드롭다운 변경. '직접 찾아보기…' 선택 시 파일 대화상자로 폼 추가."""
        data = self._form_combo.currentData()
        if data == "__BROWSE__":
            path, _ = QFileDialog.getOpenFileName(
                self, "폼지(.hwp) 선택", "",
                "한글 폼 (*.hwp *.hwpx);;모든 파일 (*.*)",
            )
            if path:
                # '직접 찾아보기…'(마지막) 앞에 항목 추가하고 선택
                self._form_combo.blockSignals(True)
                self._form_combo.insertItem(
                    self._form_combo.count() - 1, f"폼지 — {Path(path).name}", path)
                self._form_combo.setCurrentIndex(self._form_combo.count() - 2)
                self._form_combo.blockSignals(False)
                self._log(f"폼지 직접 선택: {path}")
            else:
                self._form_combo.setCurrentIndex(0)  # 취소 → 자동
            return
        label = self._form_combo.currentText()
        self._log(f"폼지 선택: {label}")

    def _resolve_form_path(self) -> str | None:
        """현재 드롭다운 선택 → 실제 폼 경로(없으면 None=기본 서식).

        자동(__AUTO__)은 파일명 규칙(학년+과목)으로 폼을 고른다(resolve_form).
        """
        data = self._form_combo.currentData()
        if data in ("__NONE__", "__BROWSE__"):
            return None
        if data == "__AUTO__":
            return resolve_form(self._selected_file or "")
        return data  # 구체 폼 경로

    # ── 변환 ──

    def _start_conversion(self):
        if not self._selected_file:
            QMessageBox.warning(self, "알림", "변환할 파일을 선택하세요.")
            return

        api_key = self._api_key_input.text().strip()
        if not api_key or api_key == "your-api-key-here":
            QMessageBox.warning(self, "알림", "Anthropic API 키를 입력하세요.")
            return

        # API 키를 config.json에 저장(Anthropic + Gemini). Gemini 키는 크롭 검출 정확도에
        # 쓰이며 비면 Claude 폴백(크롭 품질 저하)이라, 입력돼 있으면 함께 저장한다.
        from utils.config import set_api_key, set_gemini_key
        set_api_key(api_key)
        set_gemini_key(self._gemini_key_input.text().strip())

        # 폼 '자동' 모드는 파일명 규칙이 맞아야 분석(미일치 차단). 폼 직접선택/기본서식은 통과.
        info = parse_filename(self._selected_file)
        if self._form_combo.currentData() == "__AUTO__" and not info["valid"]:
            QMessageBox.warning(
                self, "파일명 규칙 확인",
                "폼 자동 채움은 파일명이 규칙과 맞아야 합니다.\n\n"
                "형식: [학교][학년][년-학기-중간/기말]([과목])\n"
                "  · 고등은 [과목] 필요(중등은 자동 수학) · 끝의 [출판사]는 있어도/없어도 됨\n"
                "예) [조암중][2][25-1-중간]   또는   [조암중][2][25-1-중간][동아강]\n"
                "예) [○○고][2][25-1-중간][대수][동아강]\n\n"
                "파일명을 맞춰 다시 올리거나, 폼 목록에서 직접 선택/‘기본 서식’을 고르세요.",
            )
            return

        output_path = self._output_input.text().strip()
        if not output_path:
            QMessageBox.warning(self, "알림", "출력 경로를 지정하세요.")
            return

        # 출력 파일 이미 존재 시 경고
        if Path(output_path).exists():
            reply = QMessageBox.warning(
                self,
                "파일 덮어쓰기 확인",
                f"이미 같은 이름의 파일이 존재합니다.\n\n"
                f"{Path(output_path).name}\n\n"
                f"덮어쓰시겠습니까?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                self._log("변환 취소: 파일 덮어쓰기 거부")
                return

        # 출력 디렉토리 생성
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        self._set_ui_converting(True)
        self._progress_bar.setValue(0)
        self._log("=" * 40)
        self._log("변환 시작...")

        # 워커 스레드 생성
        self._thread = QThread()
        self._worker = ConversionWorker(
            self._selected_file, output_path, api_key,
            template_path=self._selected_template,
            form_path=self._resolve_form_path(),   # 폼 선택(자동/수동) → 경로 or None
            header_values=(info if info["valid"] else None),  # 머리말 채움 값(파일명)
            skip_first_page=False,   # 수동 표지 스킵 폐지 — 무쓸모 페이지는 자동 스킵
            use_crop=True,           # 항상 크롭 검수 모드
            render_figures=self._render_fig_check.isChecked(),  # 그림 렌더(경고 감수) 여부
            skip_preview=self._skip_preview_check.isChecked(),  # 미리보기 생략 여부
        )
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.log.connect(self._on_log)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.quality_warning.connect(self._on_quality_warning)
        self._worker.ocr_warning.connect(self._on_ocr_warning)
        self._worker.preview_requested.connect(self._on_preview_requested)
        self._worker.crop_requested.connect(self._on_crop_requested)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)

        self._thread.start()

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

    def _set_ui_converting(self, converting: bool):
        self._convert_btn.setEnabled(not converting)
        self._cancel_btn.setEnabled(converting)
        self._browse_btn.setEnabled(not converting)
        self._output_browse_btn.setEnabled(not converting)
        self._api_key_input.setEnabled(not converting)
        self._gemini_key_input.setEnabled(not converting)
        self._form_combo.setEnabled(not converting)
        self._render_fig_check.setEnabled(not converting)
        self._skip_preview_check.setEnabled(not converting)
