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

# ── 빌드 게이트 — PyInstaller 는 datas 경로가 없어도 **경고만 내고 성공**해서, 기능이
# 조용히 빠진 도우미가 나간다(build.spec 과 같은 원칙). ⚠️ spec 의 SystemExit 은 exit
# code 0 으로 끝나므로(2026-08-07 실측) 빌드 후 산출물 검증을 반드시 병행할 것.
_forms = sorted((project_root / 'forms').glob('*.hwp'))
if len(_forms) < 7:
    raise SystemExit(f"[agent.spec] forms/*.hwp {len(_forms)}개 — 대수회 폼 7종 필요")
if not (project_root / 'resources').is_dir():
    raise SystemExit("[agent.spec] resources/ 없음 — 보안승인 DLL 필수")

a = Analysis(
    [str(project_root / 'agent.py')],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        # 한글 '파일 접근 허용' 팝업 억제 DLL — core/hwp_com.py 가 _MEIPASS/resources 에서
        # 찾아 레지스트리 등록 후 RegisterModule 로 바인딩(무인 변환 필수).
        (str(project_root / 'resources'), 'resources'),
        # ⭐ 대수회 폼 7종 — form_registry 1순위 탐색지가 _MEIPASS/forms 다. 이게 빠지면
        # 배포 도우미가 **전부 기본 서식**으로 떨어진다(파일명이 규칙에 맞아도 폼 없음).
        (str(project_root / 'forms'), 'forms'),
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
