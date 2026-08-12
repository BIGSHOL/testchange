# -*- mode: python ; coding: utf-8 -*-
"""시험지 한글화 PyInstaller 빌드 스펙."""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_all

block_cipher = None
project_root = Path(SPECPATH)

# ─────────────────────────────────────────────────────────────────────────────
# ⭐ 재현 가능한 빌드 게이트 (사용자 2026-08-07: "다른 PC 에서 빌드해도 같은 변환기")
#
# 런타임이 반드시 읽는 데이터가 **없어도 PyInstaller 는 경고만 내고 빌드가 성공**한다.
# 그러면 겉보기 정상인데 기능만 조용히 퇴화한 exe 가 나간다(단원 어휘가 없으면 메타가
# 분류표 밖 자유 생성으로 떨어짐). 그래서 여기서 **명시적으로 빌드를 실패**시킨다.
#
# ⚠️ 분류표 PDF 는 로컬 미러(D:/기출)에만 있어 다른 PC 엔 없다 —
#    그래서 **파싱 산출물 data/topic_vocab.json 을 git 에 커밋**해 둔다.
#    (재생성이 필요하면 PDF 가 있는 PC 에서 `python scripts/build_topic_vocab.py`.)
_required = [
    project_root / 'data' / 'topic_vocab.json',   # 단원 분류 어휘(정답·해설 메타)
    # ⭐ 배포 exe 에는 **대수회 폼지를 넣지 않는다**(사용자 2026-08-12). 남에게 주는
    # 빌드라 남의 폼을 동봉하지 않고, 대신 학교 기출 시험지 양식 2단 바탕만 싣는다.
    # (웹용 HWP 도우미 agent.spec 은 종전대로 대수회 폼 7종을 싣는다 — 별개 빌드.)
    project_root / 'forms' / 'plain2col',         # 2단 바탕 템플릿
    project_root / 'resources',                   # HWP 보안모듈 DLL
    project_root / '_version.py',                 # 배포 버전
]
_missing = [str(p) for p in _required if not p.exists()]
if _missing:
    raise SystemExit(
        "빌드 중단 — 필수 파일 누락(이 상태로 빌드하면 기능이 조용히 빠진 exe 가 나옵니다):\n  "
        + "\n  ".join(_missing)
        + "\n\ntopic_vocab.json 이 없다면: python scripts/build_topic_vocab.py "
          "(분류표 PDF 필요) 또는 git 에서 복원하세요."
    )

# 어휘 파일이 비었거나 깨졌으면 그것도 빌드 실패로 — 존재만으론 부족하다.
# ⚠️ try 범위는 **파싱까지만**. 안에 print 를 두면 콘솔 인코딩(cp949)이 비ASCII 문자를
#    못 찍어 UnicodeEncodeError → "파일 무효" 로 둔갑해 **정상 파일인데 빌드가 중단**된다
#    (실측 2026-08-07: em-dash 하나로 빌드 중단, 게다가 exit code 는 0 이라 성공처럼 보임).
#    PC 마다 콘솔 인코딩이 달라 이런 코드가 "PC 마다 다른 빌드 결과"를 만든다.
try:
    import json as _json
    _v = _json.loads((project_root / 'data' / 'topic_vocab.json').read_text(encoding='utf-8'))
    _n_high = sum(len(x) for x in _v.get('고등', {}).values())
    _n_mid = sum(len(x) for x in _v.get('중등', {}).values())
except Exception as _e:
    raise SystemExit(f"빌드 중단 - data/topic_vocab.json 을 읽을 수 없습니다: {_e}")
if _n_high < 100 or _n_mid < 30:
    raise SystemExit(
        f"빌드 중단 - 단원 어휘 수 부족(고등 {_n_high}, 중등 {_n_mid}). "
        "python scripts/build_topic_vocab.py 로 다시 생성하세요.")
# 진단 출력은 **ASCII 로만**(어떤 콘솔 인코딩에서도 안전).
print(f"[build.spec] topic vocab OK: high={_n_high} mid={_n_mid}")
# ─────────────────────────────────────────────────────────────────────────────

# google.genai(+전이 의존 google.auth/oauth2)는 'google' 네임스페이스 패키지라
# collect_submodules 만으론 .py 파일이 안 담긴다(google/auth 에 py.typed 만 남음).
# collect_all 로 datas/binaries/hiddenimports 를 전부 수집한다.
_google_datas, _google_binaries, _google_hidden = [], [], []
for _pkg in ('google.genai', 'google.auth', 'google.oauth2', 'google.api_core'):
    try:
        _d, _b, _h = collect_all(_pkg)
        _google_datas += _d
        _google_binaries += _b
        _google_hidden += _h
    except Exception:
        pass

# resvg_py 는 Rust 확장(.pyd + 네이티브 바이너리)이라 collect_all 로 전부 수집해야
# 동결 빌드에서 누락되지 않는다(core/figure_generator.py 그림 재생성 의존).
_resvg_datas, _resvg_binaries, _resvg_hidden = [], [], []
try:
    _resvg_datas, _resvg_binaries, _resvg_hidden = collect_all('resvg_py')
except Exception:
    pass

a = Analysis(
    [str(project_root / 'main.py')],
    pathex=[str(project_root)],
    binaries=[*_google_binaries, *_resvg_binaries],
    datas=[
        # (구) hwpx_조암 골든셋 번들은 제거 — 개발용 회귀 기준(data/골든셋기준_조암중_hwpx해제본)일 뿐
        # 런타임 코드가 읽지 않는다(2026-06-11, 5d97335 개명 때 spec 누락으로 빌드 깨짐).
        # ⭐ 2단 바탕 템플릿만 번들 → _internal/forms/plain2col/ (core/form_registry
        # .plain_form_path 가 _MEIPASS/forms/plain2col 에서 읽는다).
        # **대수회 폼지 7종은 일부러 뺐다**(사용자 2026-08-12) — 남에게 주는 빌드에 남의
        # 폼을 동봉하지 않는다. 그래서 이 exe 는 파일명이 규칙에 맞아도 폼을 못 찾고
        # `list_forms()` 가 비어 → 항상 2단 서식으로 렌더된다(gui/main_window 의
        # `render_plain_2col` 분기). 대수회 폼이 필요한 웹 경로는 agent.spec(도우미) 몫.
        (str(project_root / 'forms' / 'plain2col'), 'forms/plain2col'),
        # HWP 파일접근 보안 승인 모듈(FilePathCheckerModuleExample.dll) — core/hwp_com.py 가
        # 레지스트리 등록 후 RegisterModule 로 바인딩해 '파일 접근 허용' 팝업을 없앤다.
        (str(project_root / 'resources'), 'resources'),
        # 단원 분류표 어휘(고등 소단원 215·중등 중단원 51) — core/topic_vocab.py 가
        # _MEIPASS/data 에서 읽어 정답·해설 메타 생성 프롬프트에 싣는다. 세션이 분류표
        # PDF 를 보고 고르던 것과 **같은 어휘**를 exe 도 보게 하는 것(사용자 2026-08-07).
        (str(project_root / 'data' / 'topic_vocab.json'), 'data'),
        *collect_data_files('hwpx'),
        *_google_datas,
        *_resvg_datas,
    ],
    hiddenimports=[
        '_version',          # 배포 버전(0.1.0~) — GUI 제목·selftest 표시
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'anthropic',
        'fitz',
        'PIL',
        'lxml',
        'lxml.etree',
        'numpy',
        'matplotlib',
        # 그림 재생성 SVG→PNG 렌더러(core/figure_generator.py)
        'resvg_py',
        *_resvg_hidden,
        # Gemini 크롭 검출(core/crop_detector.py) — google.genai + 전이 의존
        # (collect_all 로 _google_hidden 에 하위모듈 전부 수집됨)
        *_google_hidden,
        # 정답·해설 자동 생성(core/solution_generator.py) — DeepSeek REST 직접 호출.
        # anthropic/google.genai 가 이미 requests 계열을 끌어오지만 명시해 둔다.
        'requests',
        'core.solution_generator',
        # HWP COM 자동화(core/hwp_com.py) — pywin32 런타임 의존성
        'win32com',
        'win32com.client',
        'win32com.gen_py',
        'pythoncom',
        'pywintypes',
        'win32api',
        *collect_submodules('hwpx'),
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        '_tkinter',
        'unittest',
        'pytest',
    ],
    noarchive=False,
    optimize=0,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='시험지한글화',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='시험지한글화',
)
