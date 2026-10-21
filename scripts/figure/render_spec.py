"""FigureSpec v2 (JSON) → 검증·정제된 SVG 한 장. **stdin → stdout 한 번**.

    echo '{"version":2,...}' | python scripts/figure/render_spec.py

성공: {"svg": "<svg …>"}   실패: {"error": "사람이 읽을 사유"}
**어떤 경우에도 0으로 끝나고 JSON 한 줄만 낸다** — 호출하는 Node 쪽
(`src/lib/figure/renderFigureSpec.ts`)이 종료 코드가 아니라 이 JSON 을 읽는다.
엔진 예외 메시지를 그대로 흘리지 않고 앞머리만 잘라 싣는다.

엔진은 이식하지 않고 그대로 호출한다(09-figure-engine-guide.md §0).
위치는 `FIGURE_ENGINE_PATH` 환경변수 — 없으면 아래 기본값.
⚠️ 문서가 적어 둔 `D:\\시험지 한글화` 는 2026-08-19 현재 **없다**. 실제는 아래 경로다.
"""

from __future__ import annotations

import io
import json
import os
import sys

# 엔진은 **저장소 안**에 있다 (원장님 지시 2026-08-19 「엔진을 우리 프로젝트로 가져와」).
# 어디를 어떤 차례로 보는가는 `engine_path` **한 곳**에 있다 — 판정기가 `elementary` 를
# 직접 import 하는 길에서도 같은 규칙이어야 한다(2026-08-28: 두 벌이던 시절 그쪽만
# `core` 를 못 찾아 시험 50개가 한꺼번에 빨개졌다).
from engine_path import VENDOR_ENGINE_PATH, engine_root  # noqa: E402

# 스펙은 LLM 이 낸 것이라 통째로 믿지 않는다. 너무 큰 입력은 엔진에 넣기 전에 끊는다.
MAX_SPEC_BYTES = 64 * 1024


def render_json(raw: str) -> dict:
    """스펙 JSON 문자열 → {"svg": …} 또는 {"error": …}. 표준입출력 진입점(main)과 Vercel 함수(api/render.py)가
    같이 부른다 — 두 벌이면 개발 서버와 배포가 다른 오류 문구를 낸다."""
    if len(raw.encode("utf-8")) > MAX_SPEC_BYTES:
        return {"error": "도형 스펙이 너무 큽니다"}
    try:
        spec = json.loads(raw)
    except Exception:
        return {"error": "도형 스펙이 올바른 JSON 이 아닙니다"}

    engine = engine_root()
    if not engine:
        return {"error": f"도형 엔진을 찾을 수 없습니다: {VENDOR_ENGINE_PATH}"}
    for entry in (engine, os.path.dirname(os.path.abspath(__file__))):
        if entry not in sys.path:
            sys.path.insert(0, entry)

    try:
        from core.figure_quality import sanitize_svg
        from core.figure_scene import render_figure_spec
        from elementary import render_elementary
    except Exception as exc:  # 엔진 자체를 못 불러온 경우 — 설정 문제다.
        return {"error": f"도형 엔진을 불러오지 못했습니다: {type(exc).__name__}"}

    try:
        # 실물 그림 조각(assets) — 엔진은 모르는 필드라 떼어 그린 뒤 맨 뒤 층에 얹는다(scene_assets.py).
        # 없으면 종전과 똑같은 길로 그린다.
        from scene_assets import render_graph_with_assets, render_v2_with_assets, split_assets
        spec, assets = split_assets(spec)
        if isinstance(spec, dict) and spec.get("version") == "graph-1":
            from graph_scene import render_graph
            svg = render_graph(spec)
            if assets is not None:
                svg = render_graph_with_assets(spec, svg, assets)
        elif isinstance(spec, dict) and spec.get("version") == "elem-1":
            if assets is not None:
                raise ValueError("assets 는 version 2·graph-1 에서만 씁니다(elem-1 은 kind:assetScene)")
            svg = render_elementary(spec)
        elif assets is not None:
            svg = render_v2_with_assets(spec, assets)
        else:
            svg = render_figure_spec(spec)
    except Exception as exc:
        # FigureSpecError/GeometryValidationError 는 **스펙이 틀렸다**는 뜻이라
        # 사유를 그대로 보여 주는 편이 낫다(원장님이 보고 판단한다). 길이는 자른다.
        return {"error": f"도형을 그리지 못했습니다: {str(exc)[:200]}"}

    try:
        # 엔진이 낸 것이라도 정제기를 통과시킨다 — 지면과 화면에 그대로 들어가는 마크업이다.
        svg = sanitize_svg(svg)
    except Exception as exc:
        return {"error": f"도형이 안전 검사를 통과하지 못했습니다: {type(exc).__name__}"}
    return {"svg": svg}


def main() -> None:
    # Windows 기본 코드페이지에서 한글 라벨이 깨진다 — 양쪽 다 UTF-8 로 못 박는다.
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    raw = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8").read()
    sys.stdout.write(json.dumps(render_json(raw), ensure_ascii=False))


if __name__ == "__main__":
    main()
