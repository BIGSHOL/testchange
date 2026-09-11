# -*- coding: utf-8 -*-
"""웹 실사용 FigureSpec 으로 도형 엔진을 잰다 — 엔진 재동기화 전후 비교용 (2026-09-11).

재료: Supabase `api_cache` kind='figure-svg' (웹 /api/figure-svg 가 Gemini 응답을 캐시한 것).
경로: 커넥터(server/convert_cli.py)와 같다 — `_compile_structured_candidate` → `assess_svg`
(배포 도우미처럼 픽셀 검사 끔, --pixel 로 켬) → resvg PNG.

사용:
    python scripts/figure_spec_ab.py --pull               # 말뭉치 갱신(config.json 의 Supabase 서비스 키)
    python scripts/figure_spec_ab.py                      # 이 저장소 엔진으로 잰다
    python scripts/figure_spec_ab.py --root D:/다른/체크아웃   # 다른 엔진(예: 옛 커밋 worktree)
    python scripts/figure_spec_ab.py --pixel --png .testkit/figab   # 픽셀 검사 + PNG 저장

⚠️ 두 엔진은 패키지 이름이 둘 다 `core` 라 한 프로세스에 같이 못 올린다 — 비교는
   `--root` 를 바꿔 **따로** 돌린다. 말뭉치(`.testkit/figure_spec_corpus.json`)는 gitignore.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CORPUS = REPO / ".testkit" / "figure_spec_corpus.json"


def pull(config_path: Path) -> None:
    cfg = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    url = (cfg.get("SUPABASE_URL") or os.environ.get("SUPABASE_URL") or "").rstrip("/")
    key = cfg.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY") or ""
    if not url or not key:
        raise SystemExit(f"Supabase URL/서비스 키가 없습니다 — {config_path} 또는 환경변수 "
                         "SUPABASE_URL·SUPABASE_SERVICE_KEY (다른 체크아웃의 config.json 은 --config)")
    req = urllib.request.Request(
        f"{url}/rest/v1/api_cache?select=key,value&kind=eq.figure-svg&limit=5000",
        headers={"apikey": key, "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        rows = json.loads(resp.read().decode("utf-8"))
    CORPUS.parent.mkdir(parents=True, exist_ok=True)
    CORPUS.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    print(f"pulled {len(rows)} rows → {CORPUS}")


def kind_of(err: str) -> str:
    for name, pat in (("의미 목록", "의미 목록"), ("각의 변 미선언", "not covered"),
                      ("치수 자리 없음", "no collision-free layout"),
                      ("직각 표시인데 직각 아님", "marked right"),
                      ("unknown field", "unknown field"), ("형식", "must be")):
        if pat in err:
            return name
    return "기타"


def run(root: Path, pixel: bool, png_dir: Path | None) -> None:
    os.environ.setdefault("MATHGEN_CONFIG_READONLY", "1")
    sys.path.insert(0, str(root))
    from core.figure_generator import _compile_structured_candidate, _svg_to_png_bytes
    from core.figure_quality import assess_svg

    rows = json.loads(CORPUS.read_text(encoding="utf-8"))
    if png_dir:
        png_dir.mkdir(parents=True, exist_ok=True)
    status, reasons, pts = Counter(), Counter(), []
    raw_ok = 0
    for i, row in enumerate(rows):
        value = row.get("value") or {}
        spec = value.get("spec")
        if not spec:
            continue
        if isinstance(spec, str):
            spec = json.loads(spec)
        cand = {"svg": value.get("svg") or "", "figure_spec": spec,
                "desc": value.get("desc") if isinstance(value.get("desc"), str) else ""}
        svg, err = _compile_structured_candidate(cand)
        if err:
            status["spec_fail"] += 1
            reasons[kind_of(err)] += 1
            fallback = assess_svg(value.get("svg") or "", run_pixel_lint=pixel)
            raw_ok += bool(fallback.accepted and fallback.sanitized_svg)
            continue
        res = assess_svg(svg or "", run_pixel_lint=pixel)
        if not (res.accepted and res.sanitized_svg):
            status["gate_reject"] += 1
            continue
        status["ok"] += 1
        m = re.search(r'viewBox="[-\d.]+ [-\d.]+ ([\d.]+) ([\d.]+)"', res.sanitized_svg)
        fs = re.findall(r'<text\b[^>]*?font-size="([\d.]+)', res.sanitized_svg)
        if m and fs:
            vw, vh = float(m.group(1)), float(m.group(2))
            insert_w = min(260, 235 * vw / vh)       # hwp_form_writer FORM_FIG_MAX_W/H
            pts.append(float(max(set(fs), key=fs.count)) * insert_w / vw * 25.4 / 96 / 0.3528)
        if png_dir:
            png = _svg_to_png_bytes(res.sanitized_svg, width=480)
            if png:
                (png_dir / f"{i:03d}.png").write_bytes(png)
    total = sum(status.values())
    pts.sort()
    print(f"engine={root} pixel={int(pixel)} | specs={total} {dict(status)} "
          f"| spec 실패→모델 SVG 통과 {raw_ok}")
    print("spec 실패 사유:", dict(reasons.most_common()))
    if pts:
        print(f"인쇄 라벨 크기(pt) 중앙 {pts[len(pts) // 2]:.2f} · 최소 {pts[0]:.2f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pull", action="store_true")
    ap.add_argument("--config", default=str(REPO / "config.json"),
                    help="--pull 이 읽을 config.json (Supabase 서비스 키)")
    ap.add_argument("--root", default=str(REPO))
    ap.add_argument("--pixel", action="store_true")
    ap.add_argument("--png", default=None)
    args = ap.parse_args()
    if args.pull:
        pull(Path(args.config))
        return 0
    if not CORPUS.exists():
        print("말뭉치가 없습니다 — 먼저 --pull", file=sys.stderr)
        return 2
    run(Path(args.root), args.pixel, Path(args.png) if args.png else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
