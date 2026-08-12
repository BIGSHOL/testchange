# -*- coding: utf-8 -*-
"""'폼 없이 2단' 렌더용 템플릿(.hwp) 제작기 — 사용자 양식 → forms/plain2col/.

대수회 폼은 **슬롯 채우기**(미주 문항 슬롯·①②③④⑤ 사전배치·정답면 container)라
구조가 맞는 폼에만 쓸 수 있다. 반면 학교에서 쓰는 평범한 2단 시험지 양식은 슬롯이
없으므로 ``write_exam_to_form`` 으로는 못 채운다 — 대신 **바탕(머리말·용지·단 설정·
단 구분선)만 물려받고 본문은 흘려 쓰는** 기본 서식 경로(``write_exam_to_hwp`` +
``template_path``)로 쓴다. 이 스크립트가 그 "바탕"을 만든다.

사람이 만든 양식을 그대로 template_path 로 주면 두 가지가 깨진다(실측 2026-08-12):

1. **본문 샘플 내용**(예시 문항·안내문·네모칸 표)이 변환물 앞에 그대로 남는다.
   → 본문만 비운다. ⚠️ ``SelectAll`` 은 **머리말까지 지운다** — 머리말이 통째로
   사라진 변환물이 나온다. ``MoveDocBegin`` + ``MoveSelDocEnd`` 로 본문만 선택할 것.
2. **개요 번호(문단 자동번호) 서식**이 남아 있으면 우리가 쓰는 문항번호와 겹쳐
   ``1. 1. 곱셈 기호…`` 처럼 **이중번호**가 인쇄된다(선택지 앞에도 ``2. ①``).
   → 본문 단락이 참조하는 paraPr 의 ``<hh:heading type="OUTLINE">`` 을 NONE 으로.
   (Ctrl+3/4 용 개요 스타일 자체는 남겨 둔다 — 본문이 안 쓰는 id 는 안 건드림.)

머리말 텍스트는 ``{{제목}}``·``{{과목}}`` 토큰으로 바꿔 둔다. 변환 때
``hwp_com_writer._fill_tokens`` 가 시험지 정보(파일명 규칙에서 파싱)로 치환한다.

사용:
    python scripts/make_plain2col_form.py "C:/…/학교 기출 시험지 양식.hwp"
    python scripts/make_plain2col_form.py <입력.hwp> --out forms/plain2col/기본2단.hwp
    python scripts/make_plain2col_form.py <입력.hwp> --keep-header   (머리말 원문 유지)
"""
from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001 — 콘솔 인코딩은 부가 기능
    pass

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from core.hwp_com import HwpSession                     # noqa: E402
from core.hwp_com_writer import _rewrite_zip            # noqa: E402

DEFAULT_OUT = REPO / "forms" / "plain2col" / "기본2단.hwp"
# 머리말에 심을 토큰 — 변환 때 _fill_tokens 가 채운다(제목="○○중 1학년 2학기 기말고사").
HEADER_TOKENS = "{{제목}}    {{과목}}"


def _mask(text: str, tag: str) -> str:
    """머리말/꼬리말 구간을 같은 길이 공백으로 덮어 본문만 남긴다(인덱스 보존)."""
    return re.sub(
        r"<hp:%s\b.*?</hp:%s>" % (tag, tag),
        lambda m: " " * len(m.group(0)),
        text,
        flags=re.S,
    )


def _body_para_pr_ids(section_xml: str) -> set[str]:
    """본문(머리말/꼬리말 제외) 단락이 쓰는 paraPr id 집합."""
    body = _mask(_mask(section_xml, "header"), "footer")
    return set(re.findall(r'paraPrIDRef="(\d+)"', body))


def _clear_outline(header_xml: str, ids: set[str]) -> tuple[str, int]:
    """지정한 paraPr 의 개요 번호(heading OUTLINE)를 NONE 으로. (xml, 바꾼 개수)"""
    n = 0

    def repl(m: re.Match) -> str:
        nonlocal n
        block = m.group(0)
        if m.group(1) not in ids or 'type="OUTLINE"' not in block:
            return block
        n += 1
        return re.sub(r'(<hh:heading[^>]*?type=")OUTLINE(")', r"\1NONE\2", block)

    return re.sub(r'<hh:paraPr id="(\d+)".*?</hh:paraPr>', repl, header_xml, flags=re.S), n


def _strip_body_text(section_xml: str) -> tuple[str, list[str]]:
    """본문에 남은 텍스트를 비운다. (xml, 지운 텍스트들)

    ⚠️ COM 으로 본문을 지운 **뒤에도** 글자가 남는 일이 있다 — 렌더/편집 중 사용자
    키 입력이 숨김 COM 문서로 새는 알려진 현상(CLAUDE '변환 중 타이핑 혼입')이 하필
    템플릿 제작 중에 걸리면 그 글자가 **템플릿에 구워져** 이후 모든 변환물 첫 문항
    앞에 붙는다(실측: 첫 시도에서 `서 ㄱ` 가 박혀 나옴 — 재렌더해도 그대로라 코드
    결함으로 오인하기 딱 좋다). 여기서 결정적으로 비운다.
    """
    head = re.search(r"<hp:header\b.*?</hp:header>", section_xml, re.S)
    foot = re.search(r"<hp:footer\b.*?</hp:footer>", section_xml, re.S)
    spans = [(m.start(), m.end()) for m in (head, foot) if m]
    removed: list[str] = []

    def in_masked(pos: int) -> bool:
        return any(a <= pos < b for a, b in spans)

    def repl(m: re.Match) -> str:
        if in_masked(m.start()) or not m.group(1):
            return m.group(0)
        removed.append(m.group(1))
        return "<hp:t></hp:t>"

    return re.sub(r"<hp:t>([^<]*)</hp:t>", repl, section_xml), removed


def _replace_header_text(section_xml: str, tokens: str) -> tuple[str, str]:
    """머리말의 첫 텍스트 런을 토큰 문자열로 교체. (xml, 원문) — 없으면 원본 그대로."""
    m = re.search(r"<hp:header\b.*?</hp:header>", section_xml, re.S)
    if not m:
        return section_xml, ""
    head = m.group(0)
    t = re.search(r"<hp:t>([^<]*)</hp:t>", head)
    if not t or not t.group(1).strip():
        return section_xml, ""
    original = t.group(1)
    new_head = head[: t.start(1)] + tokens + head[t.end(1):]
    return section_xml[: m.start()] + new_head + section_xml[m.end():], original


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="폼 없이 2단 렌더용 템플릿 제작기")
    ap.add_argument("src", help="사람이 만든 양식 .hwp/.hwpx")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help=f"출력(기본 {DEFAULT_OUT})")
    ap.add_argument("--keep-header", action="store_true",
                    help="머리말 원문 유지(토큰 치환 안 함)")
    args = ap.parse_args(argv)

    src = Path(args.src).resolve()
    out = Path(args.out).resolve()
    if not src.exists():
        sys.stderr.write(f"입력 없음: {src}\n")
        return 2
    out.parent.mkdir(parents=True, exist_ok=True)
    work = out.with_name(out.stem + ".__work.hwpx")

    # 1) 본문만 비우기(머리말/꼬리말·용지·단 설정 보존) → 작업용 .hwpx
    with HwpSession(visible=False) as s:
        s.open(src)
        s.hwp.HAction.Run("MoveDocBegin")
        s.hwp.HAction.Run("MoveSelDocEnd")   # ⚠️ SelectAll 은 머리말까지 지운다
        s.hwp.HAction.Run("Delete")
        s.save_hwpx(work)

    sec_name = "Contents/section0.xml"
    hdr_name = "Contents/header.xml"
    check = out.with_name(out.stem + ".__check.hwpx")
    print(f"입력   : {src.name}")

    # 2~4) [XML 정리 → .hwp 굽기 → 결과 재검사] 를 깨끗해질 때까지 반복.
    # ⚠️ 검사 대상은 '고친 XML' 이 아니라 **구워진 결과 파일**이다 — 굽는 세션에서도
    # 타이핑이 혼입될 수 있어서, XML 만 보면 통과했다고 착각한다(실측 2회 연속 혼입).
    for attempt in range(1, 4):
        with zipfile.ZipFile(work) as zin:
            infos = zin.infolist()
            contents = {i.filename: zin.read(i.filename) for i in infos}
        sec = contents[sec_name].decode("utf-8")
        hdr = contents[hdr_name].decode("utf-8")

        ids = _body_para_pr_ids(sec)
        hdr, n_outline = _clear_outline(hdr, ids)
        original_header = ""
        if not args.keep_header:
            sec, original_header = _replace_header_text(sec, HEADER_TOKENS)
        sec, leftover = _strip_body_text(sec)

        contents[sec_name] = sec.encode("utf-8")
        contents[hdr_name] = hdr.encode("utf-8")
        _rewrite_zip(work, infos, contents)

        # .hwp 로 굽기(HWP 가 직접 저장 → 변조 보안경고 없음, 합의 #12 와 같은 이유)
        with HwpSession(visible=False) as s:
            s.open(work)
            s.save_hwp(out)
        with HwpSession(visible=False) as s:
            s.open(out)
            s.save_hwpx(check)
        with zipfile.ZipFile(check) as z:
            final = z.read(sec_name).decode("utf-8")

        cols = re.search(r'colCount="(\d+)"', sec)
        print(f"[{attempt}회] 본문 paraPr {sorted(ids)} · 개요번호 해제 {n_outline}건 · "
              f"{cols.group(1) if cols else '?'}단 · 구분선 "
              f"{'있음' if 'colLine' in sec else '없음'}"
              + (f" · 잔여글자 제거 {leftover}" if leftover else ""))
        if original_header:
            print(f"       머리말 {original_header!r} → {HEADER_TOKENS!r}")

        body_texts = [t for t in re.findall(
            r"<hp:t>([^<]*)</hp:t>", _mask(_mask(final, "header"), "footer")) if t.strip()]
        if not body_texts:
            work.unlink(missing_ok=True)
            check.unlink(missing_ok=True)
            print(f"출력   : {out}  ({out.stat().st_size:,} bytes)")
            print("✅ 본문 비어 있음 확인")
            return 0
        # 혼입 글자가 결과에 남았다 — 방금 구운 결과를 새 작업본으로 삼아 다시 지운다.
        print(f"       ⚠ 결과에 글자 잔존 {body_texts} — 재정리")
        work.unlink(missing_ok=True)
        check.replace(work)

    work.unlink(missing_ok=True)
    check.unlink(missing_ok=True)
    print("❌ 3회 시도에도 본문이 안 비었습니다 — 변환/편집 중 타이핑을 멈추고 다시 실행하세요.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
