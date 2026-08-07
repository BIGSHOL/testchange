import json
import os
import sys
from pathlib import Path

# 프로젝트 루트 디렉토리 (exe 빌드 시 _MEIPASS 기준)
if getattr(sys, 'frozen', False):
    PROJECT_ROOT = Path(sys.executable).parent
else:
    PROJECT_ROOT = Path(__file__).parent.parent

# ─── config.json 로드 ───────────────────────────────────────
CONFIG_PATH = PROJECT_ROOT / "config.json"

_DEFAULTS = {
    "ANTHROPIC_API_KEY": "",
    "GEMINI_API_KEY": "",
    "GEMINI_MODEL": "gemini-3.5-flash",
    "OUTPUT_DIR": "",
    "CLAUDE_MODEL": "claude-sonnet-4-6",
    "CLAUDE_MAX_TOKENS": 8192,
    # ── OCR 백엔드 라우팅(2026-06-16) ─────────────────────────────────────────
    # OCR_BACKEND: "auto"(품질기반 자동) | "claude" | "gemini-pro" | "gemini-flash".
    #   auto = born-digital/고QC → flash(저렴·빠름), 스캔/손글씨 가능 → pro(충실도).
    #   Gemini 가 Sonnet 보다 5~7배 저렴해 기본을 auto(=Gemini) 로 둔다. Claude 는 폴백.
    "OCR_BACKEND": "auto",
    "GEMINI_PRO_MODEL": "gemini-3.1-pro-preview",   # messy/스캔 — 충실도 우선
    "GEMINI_FLASH_MODEL": "gemini-3.5-flash",        # clean/born-digital — 비용·속도
    "PDF_DPI": 300,
    "MAX_IMAGE_SIZE": 4096,
    "QC_MIN_WIDTH": 500,
    "QC_MIN_HEIGHT": 500,
    "QC_BLUR_THRESHOLD": 100.0,
    "QC_BLANK_THRESHOLD": 1.0,
    "QC_CONTRAST_THRESHOLD": 30.0,   # 최소 전경/배경 분리도(Otsu, 0~255). 미만이면 대비부족 경고
    "QC_PASS_SCORE": 40.0,
    # clean/messy 경계 — born-digital 이 아니어도 QC 점수가 이 값 이상이면 clean(flash).
    "QC_CLEAN_SCORE": 70.0,
    # ── 정답·해설·메타 자동 생성(2026-08-07) ──────────────────────────────────
    # 세션(Claude Code)이 사람 대신 문항을 풀어 OCR JSON 의 answer/solution/topic/difficulty
    # 를 채우던 구조를 배포 exe 에 그대로 옮긴 것 — **규약·스키마·소비 경로 동일**, 푸는
    # 주체만 외부 API(DeepSeek)로. GENERATE_SOLUTIONS 가 True 여야 동작(GUI 체크박스 연동).
    "DEEPSEEK_API_KEY": "",
    "DEEPSEEK_MODEL": "deepseek-v4-pro",              # 정답 정확도 우선(flash 대비 3배가)
    "DEEPSEEK_BASE_URL": "https://api.deepseek.com",  # OpenAI 호환 엔드포인트
    "DEEPSEEK_MAX_WORKERS": 4,     # 문항 병렬(레이트리밋 여유). 0/1 이면 직렬
    # 초 — thinking 모드라 문항당 수 초~수십 초(실측 4~13초). 재시도(HTTP 3 × 빈정답 2)와
    # 곱해지므로 너무 크면 장애 시 사용자가 오래 갇힌다(180 이면 최악 24분/문항 — 적대리뷰).
    "DEEPSEEK_TIMEOUT": 120,
    "GENERATE_SOLUTIONS": False,   # 기본 OFF(과금) — GUI 체크박스로 켠다
    # OCR 골든셋 플라이휠 — Supabase(개발/수동 업로드 전용). 비면 sync 스킵. service_role 키만.
    # ⚠️ 배포 exe 엔 넣지 않는다(서비스키는 로컬 config.json 에만). 키 이름으로 민감도 표시.
    "SUPABASE_URL": "",
    "SUPABASE_SERVICE_ROLE_KEY": "",
}

_config: dict = {}


def _load_config() -> dict:
    """config.json을 읽어 dict로 반환. 없으면 기본값으로 생성."""
    global _config
    if _config:
        return _config

    if CONFIG_PATH.exists():
        # utf-8-sig: 메모장/PowerShell 등이 붙인 BOM이 있어도 안전하게 읽는다.
        with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
            _config = json.load(f)
    else:
        # 최초 실행: 기본 config.json 생성
        _config = dict(_DEFAULTS)
        save_config(_config)

    return _config


def save_config(cfg: dict | None = None):
    """현재 설정을 config.json에 저장."""
    if cfg is None:
        cfg = _config
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def _get(key: str):
    """config에서 값 조회. 없으면 기본값 반환."""
    cfg = _load_config()
    return cfg.get(key, _DEFAULTS.get(key))


def get_api_key() -> str:
    """Anthropic API 키 반환."""
    key = str(_get("ANTHROPIC_API_KEY")).strip()
    if not key or key == "your-api-key-here":
        raise ValueError(
            "ANTHROPIC_API_KEY가 설정되지 않았습니다. "
            "config.json 파일에 API 키를 입력해주세요."
        )
    return key


def set_api_key(key: str):
    """API 키를 config에 저장."""
    cfg = _load_config()
    cfg["ANTHROPIC_API_KEY"] = key
    save_config(cfg)


def get_gemini_key() -> str:
    """Gemini API 키 반환(없으면 빈 문자열). 크롭 검출에만 사용."""
    key = str(_get("GEMINI_API_KEY") or "").strip()
    if not key:
        key = os.environ.get("GEMINI_API_KEY", "").strip()
    return key


def set_gemini_key(key: str):
    """Gemini API 키를 config 에 저장(크롭 검출용). 빈 값이면 기존 키 유지."""
    key = (key or "").strip()
    if not key:
        return
    cfg = _load_config()
    cfg["GEMINI_API_KEY"] = key
    save_config(cfg)


# Gemini 모델(크롭 검출 — bbox 그라운딩 특화)
GEMINI_MODEL = str(_DEFAULTS["GEMINI_MODEL"])


def get_supabase() -> tuple[str, str] | None:
    """Supabase (URL, service_role key) 반환. 둘 중 하나라도 없으면 None(=sync 스킵).

    OCR 골든셋 플라이휠의 개발/수동 업로드 전용. 배포 exe 엔 키가 없어 항상 None → 무동작.
    """
    url = str(_get("SUPABASE_URL") or "").strip()
    key = str(_get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if url and key:
        return url, key
    return None


def get_output_dir() -> Path:
    """기본 출력 디렉토리 반환."""
    val = _get("OUTPUT_DIR")
    output_dir = Path(val) if val else PROJECT_ROOT / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


# Claude 모델 설정
CLAUDE_MODEL = str(_DEFAULTS["CLAUDE_MODEL"])
CLAUDE_MAX_TOKENS = int(_DEFAULTS["CLAUDE_MAX_TOKENS"])

# OCR 백엔드 라우팅 설정(2026-06-16)
OCR_BACKEND = str(_DEFAULTS["OCR_BACKEND"])
GEMINI_PRO_MODEL = str(_DEFAULTS["GEMINI_PRO_MODEL"])
GEMINI_FLASH_MODEL = str(_DEFAULTS["GEMINI_FLASH_MODEL"])


def get_ocr_backend() -> str:
    """OCR 백엔드 모드 반환("auto"|"claude"|"gemini-pro"|"gemini-flash")."""
    val = str(_get("OCR_BACKEND") or "auto").strip().lower()
    return val if val in ("auto", "claude", "gemini-pro", "gemini-flash") else "auto"


# 정답·해설·메타 자동 생성(DeepSeek, 2026-08-07)
DEEPSEEK_MODEL = str(_DEFAULTS["DEEPSEEK_MODEL"])
DEEPSEEK_BASE_URL = str(_DEFAULTS["DEEPSEEK_BASE_URL"])
DEEPSEEK_MAX_WORKERS = int(_DEFAULTS["DEEPSEEK_MAX_WORKERS"])
DEEPSEEK_TIMEOUT = int(_DEFAULTS["DEEPSEEK_TIMEOUT"])


def get_deepseek_key() -> str:
    """DeepSeek API 키 반환(없으면 빈 문자열). 정답·해설 생성에만 사용."""
    key = str(_get("DEEPSEEK_API_KEY") or "").strip()
    if not key:
        key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    return key


def set_deepseek_key(key: str):
    """DeepSeek API 키를 config 에 저장. 빈 값이면 기존 키 유지."""
    key = (key or "").strip()
    if not key:
        return
    cfg = _load_config()
    cfg["DEEPSEEK_API_KEY"] = key
    save_config(cfg)


def get_generate_solutions() -> bool:
    """정답·해설·메타 자동 생성 여부(기본 False — 과금이라 명시적으로 켠다)."""
    return bool(_get("GENERATE_SOLUTIONS"))

# PDF 변환 DPI
PDF_DPI = int(_DEFAULTS["PDF_DPI"])

# 이미지 최대 크기
MAX_IMAGE_SIZE = int(_DEFAULTS["MAX_IMAGE_SIZE"])

# 품질 검사 임계값
QC_MIN_WIDTH = int(_DEFAULTS["QC_MIN_WIDTH"])
QC_MIN_HEIGHT = int(_DEFAULTS["QC_MIN_HEIGHT"])
QC_BLUR_THRESHOLD = float(_DEFAULTS["QC_BLUR_THRESHOLD"])
QC_BLANK_THRESHOLD = float(_DEFAULTS["QC_BLANK_THRESHOLD"])
QC_CONTRAST_THRESHOLD = float(_DEFAULTS["QC_CONTRAST_THRESHOLD"])
QC_PASS_SCORE = float(_DEFAULTS["QC_PASS_SCORE"])
QC_CLEAN_SCORE = float(_DEFAULTS["QC_CLEAN_SCORE"])


def _init_module_vars():
    """config.json 값으로 모듈 변수 갱신."""
    global GEMINI_MODEL, CLAUDE_MODEL, CLAUDE_MAX_TOKENS, PDF_DPI, MAX_IMAGE_SIZE
    global QC_MIN_WIDTH, QC_MIN_HEIGHT, QC_BLUR_THRESHOLD
    global QC_BLANK_THRESHOLD, QC_CONTRAST_THRESHOLD, QC_PASS_SCORE, QC_CLEAN_SCORE
    global OCR_BACKEND, GEMINI_PRO_MODEL, GEMINI_FLASH_MODEL
    global DEEPSEEK_MODEL, DEEPSEEK_BASE_URL, DEEPSEEK_MAX_WORKERS, DEEPSEEK_TIMEOUT

    cfg = _load_config()
    GEMINI_MODEL = str(cfg.get("GEMINI_MODEL", _DEFAULTS["GEMINI_MODEL"]))
    CLAUDE_MODEL = str(cfg.get("CLAUDE_MODEL", _DEFAULTS["CLAUDE_MODEL"]))
    CLAUDE_MAX_TOKENS = int(cfg.get("CLAUDE_MAX_TOKENS", _DEFAULTS["CLAUDE_MAX_TOKENS"]))
    OCR_BACKEND = str(cfg.get("OCR_BACKEND", _DEFAULTS["OCR_BACKEND"]))
    GEMINI_PRO_MODEL = str(cfg.get("GEMINI_PRO_MODEL", _DEFAULTS["GEMINI_PRO_MODEL"]))
    GEMINI_FLASH_MODEL = str(cfg.get("GEMINI_FLASH_MODEL", _DEFAULTS["GEMINI_FLASH_MODEL"]))
    PDF_DPI = int(cfg.get("PDF_DPI", _DEFAULTS["PDF_DPI"]))
    MAX_IMAGE_SIZE = int(cfg.get("MAX_IMAGE_SIZE", _DEFAULTS["MAX_IMAGE_SIZE"]))
    QC_MIN_WIDTH = int(cfg.get("QC_MIN_WIDTH", _DEFAULTS["QC_MIN_WIDTH"]))
    QC_MIN_HEIGHT = int(cfg.get("QC_MIN_HEIGHT", _DEFAULTS["QC_MIN_HEIGHT"]))
    QC_BLUR_THRESHOLD = float(cfg.get("QC_BLUR_THRESHOLD", _DEFAULTS["QC_BLUR_THRESHOLD"]))
    QC_BLANK_THRESHOLD = float(cfg.get("QC_BLANK_THRESHOLD", _DEFAULTS["QC_BLANK_THRESHOLD"]))
    QC_CONTRAST_THRESHOLD = float(cfg.get("QC_CONTRAST_THRESHOLD", _DEFAULTS["QC_CONTRAST_THRESHOLD"]))
    QC_PASS_SCORE = float(cfg.get("QC_PASS_SCORE", _DEFAULTS["QC_PASS_SCORE"]))
    QC_CLEAN_SCORE = float(cfg.get("QC_CLEAN_SCORE", _DEFAULTS["QC_CLEAN_SCORE"]))
    DEEPSEEK_MODEL = str(cfg.get("DEEPSEEK_MODEL", _DEFAULTS["DEEPSEEK_MODEL"]))
    DEEPSEEK_BASE_URL = str(cfg.get("DEEPSEEK_BASE_URL", _DEFAULTS["DEEPSEEK_BASE_URL"]))
    DEEPSEEK_MAX_WORKERS = int(cfg.get("DEEPSEEK_MAX_WORKERS", _DEFAULTS["DEEPSEEK_MAX_WORKERS"]))
    DEEPSEEK_TIMEOUT = int(cfg.get("DEEPSEEK_TIMEOUT", _DEFAULTS["DEEPSEEK_TIMEOUT"]))


_init_module_vars()
