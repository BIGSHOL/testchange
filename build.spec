# -*- mode: python ; coding: utf-8 -*-
"""시험지 한글화 PyInstaller 빌드 스펙."""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None
project_root = Path(SPECPATH)

a = Analysis(
    [str(project_root / 'main.py')],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        (str(project_root / 'hwpx_조암'), 'hwpx_조암'),
        *collect_data_files('hwpx'),
        *collect_data_files('google.genai'),
        *collect_data_files('google.auth'),
    ],
    hiddenimports=[
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
        # Gemini 크롭 검출(core/crop_detector.py) — google.genai + 전이 의존
        'google.genai',
        'google.genai.types',
        'google.auth',
        'google.oauth2',
        *collect_submodules('google.genai'),
        *collect_submodules('google.auth'),
        *collect_submodules('google.oauth2'),
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
