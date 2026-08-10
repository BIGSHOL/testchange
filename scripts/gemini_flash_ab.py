# -*- coding: utf-8 -*-
"""Gemini flash 모델 OCR A/B 프로브 — 모델 교체 검토 시 재실행용.

2026-08-10 3.5↔3.6 검토(docs/MODEL_COST_REVIEW_2026-08.md)에 쓴 하네스.
프로덕션과 같은 조건(이미지 앞·EXAM_OCR 프롬프트·temperature 0·JSON 모드·사고 끔)으로
크롭 몇 장을 두 모델에 태워 사고 토큰·출력 토큰·호출당 단가·JSON 동등성을 실측한다.

사용:
    python scripts/gemini_flash_ab.py <crop1.png> [crop2.png ...]
    (크롭 미지정 시 배포용/crop 의 강동중 p2_c0·p2_c2 를 쓴다 — 이 PC 전용 기본값)

⚠️ 실 API 과금(크롭 1장 ≈ $0.014 × 모델 수). 배포 개선 목적 호출(CLAUDE.md 예외 경로).
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from utils.config import get_gemini_key          # noqa: E402
from core.ocr_engine import (                    # noqa: E402
    active_prompt, gemini_flash_no_think_config)
from google import genai                         # noqa: E402
from google.genai import types                   # noqa: E402

DEFAULT_CROPS = [
    ROOT / "배포용/crop/[강동중][1][25-1-기말] (원본)/p2_c0.png",
    ROOT / "배포용/crop/[강동중][1][25-1-기말] (원본)/p2_c2.png",
]
# 비교할 모델 목록 — 검토 대상이 바뀌면 여기만 고친다.
MODELS = ["gemini-3.5-flash", "gemini-3.6-flash"]
PRICE = {  # USD / 1M tokens (2026-08 공식 — 갱신해서 쓸 것)
    "gemini-3.5-flash": (1.50, 9.00),
    "gemini-3.6-flash": (1.50, 7.50),
}
OUT = ROOT / ".testkit" / "_flash_ab_out"


def run(crops: list[Path]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    client = genai.Client(api_key=get_gemini_key())
    prompt = active_prompt()
    rows = []
    for model in MODELS:
        for crop in crops:
            parts = [
                types.Part.from_bytes(data=crop.read_bytes(), mime_type="image/png"),
                types.Part.from_text(text=prompt),
            ]
            kw = dict(temperature=0, max_output_tokens=8192,
                      response_mime_type="application/json")
            tc = gemini_flash_no_think_config(model)   # 프로덕션과 같은 사고-끔 분기
            if tc is not None:
                kw["thinking_config"] = tc
            t0 = time.time()
            try:
                resp = client.models.generate_content(
                    model=model, contents=parts,
                    config=types.GenerateContentConfig(**kw))
            except Exception as e:  # noqa: BLE001
                rows.append((model, crop.stem, "ERROR", str(e)[:160]))
                continue
            um = resp.usage_metadata
            pt = um.prompt_token_count or 0
            ct = um.candidates_token_count or 0
            tt = getattr(um, "thoughts_token_count", None) or 0
            pin, pout = PRICE.get(model, (0, 0))
            usd = pt / 1e6 * pin + (ct + tt) / 1e6 * pout
            (OUT / f"{model}_{crop.stem}.json").write_text(
                resp.text or "", encoding="utf-8")
            rows.append((model, crop.stem, pt, ct, tt,
                         f"{time.time() - t0:.1f}s", f"${usd:.5f}"))

    print(f"{'model':<20} {'crop':<8} {'in':>7} {'out':>7} {'think':>7} "
          f"{'time':>7} {'cost':>9}")
    for r in rows:
        print(" ".join(f"{str(c):<20}" if i == 0 else f"{str(c):>8}"
                       for i, c in enumerate(r)))

    if len(MODELS) == 2:
        a_m, b_m = MODELS
        for crop in crops:
            try:
                a = json.loads((OUT / f"{a_m}_{crop.stem}.json").read_text("utf-8"))
                b = json.loads((OUT / f"{b_m}_{crop.stem}.json").read_text("utf-8"))
            except Exception as e:  # noqa: BLE001
                print(f"[{crop.stem}] parse fail: {e}")
                continue
            qa, qb = a.get("questions") or [], b.get("questions") or []
            ident = json.dumps(a, sort_keys=True, ensure_ascii=False) == \
                json.dumps(b, sort_keys=True, ensure_ascii=False)
            print(f"[{crop.stem}] questions {len(qa)} vs {len(qb)} "
                  f"identical_json={ident}")


if __name__ == "__main__":
    argv = [Path(p) for p in sys.argv[1:]]
    run(argv or DEFAULT_CROPS)
