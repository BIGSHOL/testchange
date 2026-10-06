# -*- coding: utf-8 -*-
"""대수회 폼지(.hwp)를 `forms/` 로 들여온다 — 폼 개정 때마다 같은 절차를 재현하려는 도구.

    python scripts/import_daesu_forms.py "<새 폼이 든 폴더>" [--glob "*폼지 최종(10.05)*.hwp"]

하는 일:
  1. 고등 폼은 **바이트 그대로 복사**한다.
  2. 중등 폼(`(중1용)`·`(중2용)`·`(중3용)`)은 메타란 라벨 `[소단원]` 을 `[중단원]` 으로
     바꿔서 저장한다(사용자 2026-10-06 "소단원은 중단원으로 바꿔서 가져오면 된다").
     26년 개정 폼은 중등도 `[소단원]` 으로 깔려 왔지만 분류 체계는 고등=소단원(ⅰ 레벨) /
     중등=중단원(① 레벨)이다(CLAUDE.md '정답·해설·메타 자동 생성').
  3. 들여온 결과를 `.hwpx` 로 떠서 **원본과 텍스트를 대조**한다 — 라벨 치환 말고는 한 글자도
     달라지면 안 된다. ⚠️ 폼 제작 중 사용자 키 입력이 숨김 COM 문서로 새면 그 글자가 **폼에
     구워져** 이후 모든 변환물에 찍힌다(2026-08-12 `기본2단.hwp` 에서 2회 연속 실측).
     어긋나면 그 폼은 건너뛰고 실패로 보고한다(다시 실행하면 된다 — 혼입은 비결정).

기존 `forms/*.hwp` 는 건드리지 않는다(교체는 호출자가 `git rm` 으로 — 이력에 남게).
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from core.hwp_com import HwpSession  # noqa: E402

FORMS = REPO / "forms"
_MIDDLE_RE = re.compile(r"\(중\s*[1-3]\s*용\)")
_SRC_LABEL, _DST_LABEL = "[소단원]", "[중단원]"


def _body_text(hwpx: Path) -> str:
    """본문 구역의 태그 뺀 텍스트(수식 스크립트 포함) — 대조용."""
    with zipfile.ZipFile(hwpx) as z:
        out = []
        for n in sorted(z.namelist()):
            if re.search(r"section\d+\.xml$", n):
                out.append(re.sub(r"<[^>]+>", "", z.read(n).decode("utf-8")))
    return "".join(out)


def _to_hwpx(hwp: Path, hwpx: Path) -> None:
    with HwpSession(visible=False) as ses:
        ses.open(hwp)
        ses.save_hwpx(hwpx)


def _relabel(src: Path, dst: Path) -> None:
    """src(.hwp) 를 열어 라벨을 바꾸고 dst(.hwp) 로 저장."""
    with HwpSession(visible=False) as ses:
        h = ses.hwp
        ses.open(src)
        fr = h.HParameterSet.HFindReplace
        h.HAction.GetDefault("AllReplace", fr.HSet)
        fr.FindString = _SRC_LABEL
        fr.ReplaceString = _DST_LABEL
        fr.Direction = h.FindDir("AllDoc")
        fr.ReplaceMode = 1
        fr.IgnoreMessage = 1
        fr.FindType = 1
        h.HAction.Execute("AllReplace", fr.HSet)
        ses.save_hwp(dst)


def import_one(src: Path, work: Path) -> tuple[bool, str]:
    dst = FORMS / src.name
    middle = bool(_MIDDLE_RE.search(src.name))
    # COM 은 사본으로만 연다(원본 폴더의 파일은 읽기만).
    a = work / "src.hwp"
    shutil.copy2(src, a)
    if not middle:
        shutil.copy2(src, dst)
        return True, "복사"
    b = work / "out.hwp"
    _relabel(a, b)
    ax, bx = work / "src.hwpx", work / "out.hwpx"
    _to_hwpx(a, ax)
    _to_hwpx(b, bx)
    before, after = _body_text(ax), _body_text(bx)
    n_src = before.count(_SRC_LABEL)
    if not n_src:
        return False, f"원본에 {_SRC_LABEL} 가 없다"
    if after.count(_SRC_LABEL) or after.count(_DST_LABEL) != n_src + before.count(_DST_LABEL):
        return False, (f"치환 불완전 — 남은 {_SRC_LABEL} {after.count(_SRC_LABEL)}개, "
                       f"{_DST_LABEL} {after.count(_DST_LABEL)}개(기대 {n_src})")
    if before.replace(_SRC_LABEL, _DST_LABEL) != after:
        return False, "라벨 말고도 본문이 달라졌다(타이핑 혼입 의심) — 다시 실행할 것"
    shutil.copy2(b, dst)
    return True, f"{_SRC_LABEL}→{_DST_LABEL} {n_src}곳"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("src_dir")
    ap.add_argument("--glob", default="*.hwp")
    args = ap.parse_args()
    files = sorted(Path(args.src_dir).glob(args.glob))
    if not files:
        print("들여올 폼이 없다:", args.src_dir, args.glob)
        return 1
    bad = 0
    for f in files:
        with tempfile.TemporaryDirectory(prefix="formimp_") as td:
            try:
                ok, msg = import_one(f, Path(td))
            except Exception as e:  # noqa: BLE001 — COM 크래시도 그 폼만 실패로
                ok, msg = False, f"{type(e).__name__}: {e}"
        print(("OK  " if ok else "FAIL"), f.name, "—", msg)
        bad += 0 if ok else 1
    print(f"\n{len(files) - bad}/{len(files)} 들여옴 → {FORMS}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
