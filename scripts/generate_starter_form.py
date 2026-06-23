# -*- coding: utf-8 -*-
"""스타터 폼 생성기 — 템플릿 헤더를 {{토큰}}으로 그린 .hwpx 골격을 만든다.

사용자가 이 골격을 한글에서 열어 색·폰트·표·머릿말/꼬릿말을 다듬은 뒤 forms/ 에
저장하면(예: forms/jeongtong.hwpx), 커넥터가 변환 때 그 폼을 template_path 로 써서
*픽셀 완벽* 헤더를 쓰고 {{토큰}}을 시험지 정보로 치환한다(§내보내기 고도화 — 폼 우선).

실행 (한글 설치 PC, Python 3.11 + pywin32):
    py -3.11 scripts/generate_starter_form.py jeongtong
    py -3.11 scripts/generate_starter_form.py jeongtong --out forms/jeongtong_starter.hwpx

기본 출력: <엔진루트>/forms/<template>_starter.hwpx
다듬은 최종 폼은 forms/<template>.hwpx (확장자 .hwp 도 인식) 로 저장해야 자동 적용된다.
"""
import sys
import argparse
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ENGINE_ROOT = Path(__file__).resolve().parent.parent
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

TEMPLATES = ("pyeongga", "jeongtong", "modern", "workbook", "jaseup", "yuhyung")


def main() -> int:
    ap = argparse.ArgumentParser(description="스타터 폼(.hwpx) 생성기")
    ap.add_argument("template", nargs="?", default="jeongtong",
                    help=f"템플릿 id {TEMPLATES} (기본 jeongtong)")
    ap.add_argument("--out", default=None, help="출력 .hwpx 경로(기본 forms/<t>_starter.hwpx)")
    ap.add_argument("--visible", action="store_true", help="한글 창을 보이게 띄움")
    args = ap.parse_args()

    template = args.template
    if template not in TEMPLATES:
        sys.stderr.write(f"알 수 없는 template: {template} — {TEMPLATES} 중 하나\n")
        return 2

    out = Path(args.out) if args.out else ENGINE_ROOT / "forms" / f"{template}_starter.hwpx"
    out.parent.mkdir(parents=True, exist_ok=True)

    from core.hwp_com import HwpSession
    from core.template_headers import (
        generate_form_layout,
        resolve_accent_rgb,
        starter_meta,
    )

    meta = starter_meta(template)
    accent = resolve_accent_rgb(template, "")
    with HwpSession(visible=args.visible) as s:
        s.set_char_size(s.base_pt)
        # 머릿말(러닝 헤더) + 자동 페이지번호 + 본문 page-1 블록 — 모두 {{토큰}} 골격.
        # 변환 시 커넥터가 이 폼을 열어 본문 뒤로 문항을 흘리고 토큰을 치환한다.
        generate_form_layout(s, template, meta, accent)
        s.save_hwpx(out)

    # 좁은 쪽 여백 + 헤더 표 열너비를 폼에 박는다(저장 후 XML 패치) — 변환 출력이 그대로 상속.
    # 열너비: HWP TableCreate 가 col_widths 를 균등 재배분하므로 XML 로 직접 재분배(긴 시험일·
    # 점수 칸 뭉개짐/줄바꿈 방지). _set_page_margins 와 동일 패턴.
    from core.hwp_com_writer import (
        _set_page_margins, _set_header_col_widths, _shade_header_labels,
        _style_header_runs, _thicken_header_outer_borders,
    )
    try:
        _set_page_margins(out)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"(여백 설정 경고: {e})\n")
    try:
        nfix = _set_header_col_widths(out)
        sys.stderr.write(f"(헤더 열너비 패치: {nfix}개 표)\n")
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"(열너비 설정 경고: {e})\n")
    try:
        nshade = _shade_header_labels(out)
        sys.stderr.write(f"(헤더 라벨 음영: {nshade}개 셀)\n")
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"(라벨 음영 경고: {e})\n")
    try:
        nstyle = _style_header_runs(out)
        sys.stderr.write(f"(헤더 글자 스타일: {nstyle}개 런)\n")
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"(글자 스타일 경고: {e})\n")
    try:
        nborder = _thicken_header_outer_borders(out)
        sys.stderr.write(f"(헤더 바깥 테두리 굵게: {nborder}개 셀)\n")
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"(테두리 경고: {e})\n")

    if not out.exists():
        sys.stderr.write("save 완료했으나 출력 파일이 없습니다.\n")
        return 3
    sys.stderr.write(
        f"OK 스타터 폼 생성: {out} ({out.stat().st_size} bytes)\n"
        f"   - 머릿말(러닝 헤더) + 자동 페이지번호 + 본문 시험정보 블록이 이미 들어 있습니다.\n"
        f"→ 한글에서 열어 색·폰트·표 디자인을 다듬은 뒤 forms/{template}.hwpx 로 저장하세요.\n"
        f"  ({{{{토큰}}}} 글자(예: {{{{학교}}}})는 그대로 두세요 — 변환 때 시험지 정보로 치환됩니다.)\n"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
