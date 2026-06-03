"""이미지 품질 사전 검사 모듈.

API 호출 전에 이미지 품질을 검사하여 흐린 스캔, 빈 페이지 등
불필요한 과금을 방지합니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from utils.config import (
    QC_MIN_WIDTH,
    QC_MIN_HEIGHT,
    QC_BLUR_THRESHOLD,
    QC_BLANK_THRESHOLD,
    QC_CONTRAST_THRESHOLD,
    QC_PASS_SCORE,
)


@dataclass
class ImageQuality:
    """이미지 품질 검사 결과."""

    score: float = 100.0          # 0~100 품질 점수
    passed: bool = True           # 합격 여부
    warnings: list[str] = field(default_factory=list)

    # 세부 측정값
    width: int = 0
    height: int = 0
    blur_score: float = 0.0       # Laplacian 분산 (높을수록 선명)
    blank_ratio: float = 0.0      # 비백색 픽셀 비율 (%)
    contrast_sep: float = 0.0     # 전경(잉크)/배경(종이) 평균밝기 분리도 (Otsu, 밀도 무관)


def check_image_quality(image: Image.Image) -> ImageQuality:
    """이미지 품질을 종합 검사.

    Args:
        image: 검사할 PIL Image

    Returns:
        ImageQuality 결과
    """
    result = ImageQuality()
    arr = np.array(image.convert("RGB"))

    # 1) 해상도 체크
    result.width, result.height = image.size
    _check_resolution(result)

    # 2) 그레이스케일 변환 (블러/대비 측정용)
    gray = np.array(image.convert("L"), dtype=np.float64)

    # 3) 흐림 감지
    result.blur_score = _compute_laplacian_variance(gray)
    _check_blur(result)

    # 4) 빈 페이지 감지
    result.blank_ratio = _compute_non_white_ratio(arr)
    _check_blank(result)

    # 5) 대비 부족 감지 — 전체 표준편차(np.std)는 문서에서 '잉크 밀도'에 좌우되어
    #    여백 많은/획 얇은 수식 페이지를 오탐한다(std ≈ √(f(1−f))·(종이−잉크)).
    #    전경/배경 분리도(Otsu)로 밀도와 무관하게 실제 가독 대비만 측정.
    result.contrast_sep = _compute_contrast_separation(gray)
    _check_contrast(result)

    # 최종 합격 판정
    result.passed = result.score >= QC_PASS_SCORE
    return result


# ─── 개별 검사 함수 ──────────────────────────────────────────


def _check_resolution(result: ImageQuality) -> None:
    if result.width < QC_MIN_WIDTH or result.height < QC_MIN_HEIGHT:
        penalty = 30.0
        result.score -= penalty
        result.warnings.append(
            f"해상도 부족: {result.width}x{result.height} "
            f"(최소 {QC_MIN_WIDTH}x{QC_MIN_HEIGHT})"
        )


def _compute_laplacian_variance(gray: np.ndarray) -> float:
    """Laplacian 필터의 분산으로 선명도 측정."""
    # 간단한 3x3 Laplacian 커널 적용 (scipy/cv2 없이 구현)
    kernel = np.array([[0, 1, 0],
                       [1, -4, 1],
                       [0, 1, 0]], dtype=np.float64)
    h, w = gray.shape
    # 패딩된 이미지
    padded = np.pad(gray, 1, mode="edge")
    laplacian = np.zeros_like(gray)
    for dy in range(3):
        for dx in range(3):
            laplacian += kernel[dy, dx] * padded[dy:dy + h, dx:dx + w]
    return float(np.var(laplacian))


def _check_blur(result: ImageQuality) -> None:
    if result.blur_score < QC_BLUR_THRESHOLD:
        penalty = 40.0
        result.score -= penalty
        result.warnings.append(
            f"이미지가 흐림: 선명도 {result.blur_score:.1f} "
            f"(기준 {QC_BLUR_THRESHOLD})"
        )


def _compute_non_white_ratio(arr: np.ndarray) -> float:
    """비백색 픽셀 비율(%) 계산."""
    # 각 픽셀의 밝기 (R+G+B)/3
    brightness = arr.mean(axis=2)
    # 240 이상을 '백색'으로 간주
    non_white = np.sum(brightness < 240)
    total = brightness.size
    return float(non_white / total * 100)


def _check_blank(result: ImageQuality) -> None:
    if result.blank_ratio < QC_BLANK_THRESHOLD:
        penalty = 50.0
        result.score -= penalty
        result.warnings.append(
            f"빈 페이지 의심: 내용 비율 {result.blank_ratio:.2f}% "
            f"(기준 {QC_BLANK_THRESHOLD}%)"
        )


def _otsu_threshold(gray: np.ndarray) -> int:
    """Otsu 이진화 임계값(클래스간 분산 최대화). cv2 없이 numpy 벡터화."""
    hist = np.bincount(
        gray.astype(np.int64).ravel(), minlength=256)[:256].astype(np.float64)
    levels = np.arange(256, dtype=np.float64)
    w_b = np.cumsum(hist)               # 임계값 이하(어두운 전경) 누적 화소수
    w_f = gray.size - w_b               # 임계값 초과(밝은 배경) 화소수
    sum_total = float(np.dot(levels, hist))
    sum_b = np.cumsum(levels * hist)
    m_b = np.divide(sum_b, w_b, out=np.zeros(256), where=w_b > 0)
    m_f = np.divide(sum_total - sum_b, w_f, out=np.zeros(256), where=w_f > 0)
    var_between = w_b * w_f * (m_b - m_f) ** 2
    return int(np.argmax(var_between))


def _compute_contrast_separation(gray: np.ndarray) -> float:
    """전경(잉크)·배경(종이) 평균 밝기 차(0~255). 잉크 밀도와 무관한 실제 대비.

    Otsu 임계값으로 두 군집을 나눈 뒤 평균차를 반환. 선명한 인쇄는 ~180+,
    바랜 스캔은 낮아진다. 균일/단색 이미지는 한쪽 군집이 비어 0.
    """
    t = _otsu_threshold(gray)
    fg = gray[gray <= t]    # 어두운 전경(잉크): Otsu 임계값 이하 (class0)
    bg = gray[gray > t]     # 밝은 배경(종이): 임계값 초과
    if fg.size == 0 or bg.size == 0:
        return 0.0
    return float(bg.mean() - fg.mean())


def _check_contrast(result: ImageQuality) -> None:
    # 분리도 < 기준(기본 30)은 잉크와 종이가 거의 안 갈리는 '바랜/저대비' 스캔.
    # (정상 흑백 인쇄는 분리도가 높아 밀도가 낮아도 걸리지 않는다.)
    if result.contrast_sep < QC_CONTRAST_THRESHOLD:
        penalty = 25.0
        result.score -= penalty
        result.warnings.append(
            f"대비 부족: 전경/배경 분리 {result.contrast_sep:.1f} "
            f"(기준 {QC_CONTRAST_THRESHOLD})"
        )
