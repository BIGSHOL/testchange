# -*- coding: utf-8 -*-
"""meta.json 에 렌더·검수 결과 기록."""
import json
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "meta.json"
m = json.loads(p.read_text(encoding="utf-8"))
m["status"] = "reviewed"
m["render"] = {
    "harness": ".testkit/_s26_render.py (26년 개정 중2 폼, 그림 16개 실삽입)",
    "pages": "8쪽 — 문제 1~5쪽, 빈 6쪽(패리티), 정답·해설 7~8쪽",
    "gates": ("corpus_lint --xml PASS(0 WARN) · 이상문자열 0 · 그림 17(배너 1 + 본문 16, binItem 전부 별개) · "
              "수식 352개 전부 baseUnit 1100 · 2회 렌더 쪽 배치 동일"),
    "review": "원본 PDF ↔ 쪽 PNG 전 문항 직접 대조(2026-10-06). 서답형 라벨은 통일 규칙(2026-08-20)대로 [서술형 N].",
    "fix": ("B형 1건 — 프라임 뒤 \\sim 이 단항(부정 ∼)으로 떨어짐(서답형6 해설 △AGG'∽△AEF) → "
            "latex_to_hwpeq _SIM_OPERAND_TAIL 에 프라임 추가"),
    "delivered": r"C:\Users\user\Downloads\[사대부중][2][25-2-기말][비상] (워드).hwp",
}
p.write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("meta ok")
