# -*- mode: python ; coding: utf-8 -*-
"""시험지 한글화 PyInstaller 빌드 스펙."""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_all

block_cipher = None
project_root = Path(SPECPATH)

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
        (str(project_root / 'hwpx_조암'), 'hwpx_조암'),
        # 대수회 폼지(학년별 색상 7종) 번들 → _internal/forms/ (core/form_registry 가 _MEIPASS/forms 에서 읽음)
        (str(project_root / 'forms'), 'forms'),
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
