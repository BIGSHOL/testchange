# -*- mode: python ; coding: utf-8 -*-
"""MathGen HWP 도우미(트레이 커넥터) PyInstaller 스펙.

전체 GUI 빌드(build.spec)와 달리 *변환 경로*(parse_ocr_response → build_document →
write_exam_to_hwp[COM])와 커넥터 + 트레이만 번들한다. GUI/OCR/figure/AI 의존
(PySide6·fitz·matplotlib·numpy·resvg·google·anthropic)은 변환에 불필요 → 제외해 경량화.

타깃 PC 엔 한글(HWP) 외 설치 불필요. onedir(빠른 자기 재호출 — connector 의
--convert-worker 자식 프로세스 COM 격리). console=False(트레이, 콘솔창 없음).
"""
from pathlib import Path

block_cipher = None
project_root = Path(SPECPATH)

a = Analysis(
    [str(project_root / 'agent.py')],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        # 한글 '파일 접근 허용' 팝업 억제 DLL — core/hwp_com.py 가 _MEIPASS/resources 에서
        # 찾아 레지스트리 등록 후 RegisterModule 로 바인딩(무인 변환 필수).
        (str(project_root / 'resources'), 'resources'),
    ],
    hiddenimports=[
        # HWP COM 자동화(core/hwp_com.py) — pywin32 동적 디스패치라 정적 추적 안 됨.
        'win32com', 'win32com.client', 'win32com.gen_py',
        'pythoncom', 'pywintypes', 'win32api',
        # 시스템 트레이.
        'pystray', 'pystray._win32', 'PIL', 'PIL.Image', 'PIL.ImageDraw',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 변환 경로 무관 — 전부 GUI/OCR/figure/AI 의존. 번들 경량화(+빌드 속도).
        'PySide6', 'shiboken6', 'matplotlib', 'fitz', 'pymupdf',
        'numpy', 'scipy', 'pandas', 'resvg_py',
        'google', 'google.genai', 'google.auth', 'anthropic', 'httpx',
        'tkinter', '_tkinter', 'unittest', 'pytest', 'IPython',
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
    name='MathGenHWP',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                # UPX 압축 비활성 — AV 오탐 + 미설치 회피
    console=False,            # 트레이 앱 — 콘솔창 없음
    disable_windowed_traceback=False,
    argv_emulation=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='MathGenHWP',
)
