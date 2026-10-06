# -*- coding: utf-8 -*-
"""SVG 품질 게이트 — **전면 배경 rect 는 반려 사유가 아니다** (stdlib·API 0원).

⭐⭐ 실사고(대륜고 공수2 웹 변환, 2026-08-20): 모델이 습관적으로 넣은 배경용
``<rect width="400" height="280" fill="none"/>`` **하나 때문에** 멀쩡한 무리함수
그래프가 통째로 반려돼 "※ 그림 자리" 안내문구로 떨어졌다. 캔버스를 통째로 덮는
rect 는 특정 도형을 흉내 낼 수 없어(모든 걸 덮는다) '숨긴 내용' 위협모델과 무관하다.

⚠️ **넓게 풀면 안 된다** — 이 게이트는 "안 보이는 요소로 내용을 있는 척하는" 생성물을
막는 장치다. 그래서 **부분** 크기의 안 보이는 도형·투명 라벨은 계속 차단해야 한다
(선 없는 사각형 = 원본에 있던 테두리가 빠진 것 → 원본 크롭 폴백이 맞다).
이 테스트는 그 경계를 양쪽에서 박제한다.

실행: .venv\\Scripts\\python.exe tests/test_figure_gate_warnings.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

for _s in (sys.stdout, sys.stderr):
    try:                        # cp949 콘솔에서 비ASCII print 가 죽는 것 방지
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

FAILED: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  OK   {label}")
    else:
        FAILED.append(label)
        print(f"  FAIL {label}" + (f" — {detail}" if detail else ""))


def _svg(body: str, w: int = 200, h: int = 120) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
            f'width="{w}" height="{h}">{body}</svg>')


_GRAPH = ('<line x1="10" y1="110" x2="190" y2="110" stroke="#000" stroke-width="2"/>'
          '<path d="M 20,20 C 80,40 140,80 180,105" fill="none" stroke="#000" '
          'stroke-width="2"/>')


def main() -> int:
    from core.figure_quality import assess_svg

    print("A. 전면 배경 rect 는 통과(실사고 재현)")
    for fill in ('fill="none"', 'fill="transparent"', 'fill="#ffffff"', 'fill="white"'):
        r = assess_svg(_svg(f'<rect width="200" height="120" {fill} />' + _GRAPH),
                       run_pixel_lint=False)
        check(f"배경 rect {fill} 가 있어도 통과", r.accepted, str(r.issues))
    # 좌표를 명시한 형태(x=0 y=0)도 같은 배경이다.
    r = assess_svg(_svg('<rect x="0" y="0" width="200" height="120" fill="none"/>'
                        + _GRAPH), run_pixel_lint=False)
    check("x/y 를 명시한 전면 rect 도 통과", r.accepted, str(r.issues))

    print("B. 게이트를 약화시키지 않았다")
    r = assess_svg(_svg('<rect x="20" y="20" width="50" height="30" fill="none"/>'
                        + _GRAPH), run_pixel_lint=False)
    check("**부분** 크기의 안 보이는 rect 는 여전히 반려", not r.accepted, str(r.issues))
    r = assess_svg(_svg('<rect width="200" height="120" fill="none" />'
                        '<path d="M 10,10 L 50,50" fill="none" />'), run_pixel_lint=False)
    check("배경만 있고 보이는 도형이 없으면 반려", not r.accepted, str(r.issues))
    check("반려 사유는 '보이는 도형 없음'",
          any("no visible geometric primitive" in i for i in r.issues), str(r.issues))
    r = assess_svg(_svg('<g fill="#0000"><text x="50" y="50">A</text></g>' + _GRAPH),
                   run_pixel_lint=False)
    check("투명 라벨(숨긴 내용)은 여전히 반려", not r.accepted, str(r.issues))

    print("C. 보안 경계는 그대로")
    r = assess_svg(_svg('<script>alert(1)</script>' + _GRAPH), run_pixel_lint=False)
    check("script 는 정제/차단",
          not r.accepted or "script" not in (r.sanitized_svg or ""),
          str(r.issues) + str(r.security_issues))

    print("\n전부 통과" if not FAILED else f"\n{len(FAILED)}건 FAIL:\n  - "
          + "\n  - ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
