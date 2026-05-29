"""PDF를 페이지별 이미지로 변환하는 모듈."""

from __future__ import annotations

import io
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image

from utils.config import PDF_DPI, MAX_IMAGE_SIZE


def pdf_to_images(pdf_path: str | Path) -> list[Image.Image]:
    """PDF 파일을 페이지별 PIL Image 리스트로 변환.

    Args:
        pdf_path: PDF 파일 경로

    Returns:
        페이지별 PIL Image 리스트
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF 파일을 찾을 수 없습니다: {pdf_path}")

    doc = fitz.open(str(pdf_path))
    images = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        # 300 DPI로 렌더링
        zoom = PDF_DPI / 72  # 72 DPI가 기본
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)

        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data))
        img = _resize_if_needed(img)
        images.append(img)

    doc.close()
    return images


def load_image(image_path: str | Path) -> Image.Image:
    """이미지 파일을 PIL Image로 로드.

    Args:
        image_path: 이미지 파일 경로

    Returns:
        PIL Image
    """
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {image_path}")

    img = Image.open(str(image_path))
    if img.mode != "RGB":
        img = img.convert("RGB")
    img = _resize_if_needed(img)
    return img


def _resize_if_needed(img: Image.Image) -> Image.Image:
    """이미지가 최대 크기를 초과하면 리사이즈."""
    w, h = img.size
    if w > MAX_IMAGE_SIZE or h > MAX_IMAGE_SIZE:
        ratio = min(MAX_IMAGE_SIZE / w, MAX_IMAGE_SIZE / h)
        new_size = (int(w * ratio), int(h * ratio))
        img = img.resize(new_size, Image.LANCZOS)
    return img


def image_to_base64(img: Image.Image, format: str = "PNG") -> str:
    """PIL Image를 base64 문자열로 변환."""
    import base64

    buffer = io.BytesIO()
    img.save(buffer, format=format)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def _row_line_variance(img: Image.Image) -> float:
    """가로 텍스트 라인 구조 강도(행별 어두운 픽셀 수의 분산). 정상 세로 문서일수록 큼."""
    import numpy as np
    g = np.asarray(img.convert("L").resize((300, 300)), dtype=float)
    bw = g < (g.mean() - 8)
    return float(np.var(bw.sum(axis=1)))


def detect_and_correct_rotation(image: Image.Image) -> Image.Image:
    """명백히 90° 누운(가로) 페이지만 보수적으로 세로로 보정.

    디지털 PDF(이미 세로)·정상 이미지는 그대로 둔다(오보정 방지). 가로(w>h)인
    경우에만 시계/반시계 90° 두 후보 중 '가로 텍스트 라인 구조'가 강한 쪽 선택.
    180°(상하반전)는 투영만으로 구분 불가라 다루지 않음.
    """
    w, h = image.size
    if w <= h * 1.15:          # 세로 또는 거의 정사각 → 정상으로 간주
        return image
    cw = image.rotate(-90, expand=True)   # 시계방향 90
    ccw = image.rotate(90, expand=True)   # 반시계방향 90
    return cw if _row_line_variance(cw) >= _row_line_variance(ccw) else ccw


def get_supported_extensions() -> set[str]:
    """지원하는 파일 확장자 집합 반환."""
    return {".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif"}


def is_pdf(path: str | Path) -> bool:
    """PDF 파일 여부 확인."""
    return Path(path).suffix.lower() == ".pdf"
