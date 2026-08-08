# -*- coding: utf-8 -*-
"""exe 경로 ↔ 웹 경로 **결과물 차등 대조** (외부 API 0원, 캐시 corpus 사용).

⭐ "웹이 exe 와 100% 같은 .hwp 를 만든다"는 주장은 **같은 입력으로 같은 문서가 나온다**는
걸 보여야 성립한다. 두 경로는 렌더 직전까지가 다르고, 그 뒤(write_exam_to_form)는 공유
코드다 — 따라서 **렌더 직전 ExamDocument 가 같으면 .hwp 도 같다.**

  exe 경로:  OCR JSON → gui 워커 _resolve_figures → parse_ocr_response → build_document
  웹 경로:   OCR JSON → (서버 JSON 직렬화) → 브라우저 → (JSON 직렬화) → 커넥터
                       → convert_cli.resolve_figures → parse_ocr_response → build_document

⚠️ 웹 경로에는 **HTTP JSON 2홉**이 있다. 자바스크립트는 `3.0` 과 `3` 을 구분하지 못하므로
(JSON.stringify(3.0) === "3") 이 왕복에서 float 가 int 로 접힌다 — 이 손실을 정확히
재현해야 진짜 차이를 볼 수 있다(`_js_json_roundtrip`).

⚠️⚠️ **이 하네스의 사각지대 — 반드시 알고 쓸 것.**
캐시된 **같은 OCR JSON 에서 출발**하므로, 증명 범위는 딱 "OCR JSON → .hwp" 구간이다.
그 앞뒤는 하나도 증명하지 못한다:

  · **OCR 요청 자체**(프롬프트 본문·이미지/프롬프트 순서·모델·JSON 모드) — 여기가 갈리면
    애초에 다른 OCR JSON 이 나오는데 이 하네스는 늘 초록불이다. 실제로 크롭 프롬프트가
    385자 손본으로 들어가 있던 것을 이 하네스는 못 잡았다.
  · **정답·해설 경로**(`solution_generator`) — 정답·해설·단원·난이도는 이 비교 대상 밖이다.
    `\\b` 한글 경계, 코드펜스 제거 누락이 여기 숨어 있었다.
    → 그 구간은 웹 저장소의 `scripts/test-solution-normalize.mjs`(정규화 4종 차등)와
      `scripts/verify-against-engine.mjs`(프롬프트 글자 단위 동일)가 맡는다.

즉 **이 셋을 다 통과해야** "exe 와 웹이 같다"가 성립한다. 하나만 보고 단정하지 말 것.

실행:
  python scripts/web_exe_diff.py            # corpus 전체
  python scripts/web_exe_diff.py 경원고 상인고  # 이름에 포함된 것만
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# ── 웹의 JSON 왕복 손실을 정확히 재현 ────────────────────────────────────────
def _js_number(v):
    """JS 의 숫자 직렬화를 흉내: 정수값 float 는 int 로 접힌다(3.0 → 3)."""
    if isinstance(v, bool):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def _js_json_roundtrip(obj):
    """서버→브라우저→커넥터 2홉을 거친 결과(JS 숫자 의미론 적용)."""
    if isinstance(obj, dict):
        return {k: _js_json_roundtrip(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_js_json_roundtrip(v) for v in obj]
    return _js_number(obj)


# ── 문서 직렬화(비교용) ──────────────────────────────────────────────────────
def _block_sig(b) -> dict:
    d = {"type": getattr(getattr(b, "type", None), "name", str(getattr(b, "type", ""))),
         "value": getattr(b, "value", None)}
    for f in ("rows", "bold", "underline", "italic", "box_member", "force_equation"):
        v = getattr(b, f, None)
        if v:
            d[f] = v
    return d


def _q_sig(q) -> dict:
    from core.hwp_com_writer import score_str

    # ⚠️ 배점은 **렌더되는 문자열**로 비교한다. 타입(float 3.0 vs int 3)은 JSON 왕복에서
    # 필연적으로 갈리지만, 인쇄되는 글자가 같으면 산출물은 동일하다 — 판정 기준은 후자다.
    sc = getattr(q, "score", None)
    sig = {
        "number": getattr(q, "number", None),
        "score": None if sc is None else score_str(sc),
        "label_type": getattr(q, "label_type", None),
        "topic": getattr(q, "topic", None),
        "difficulty": getattr(q, "difficulty", None),
        "contents": [_block_sig(b) for b in getattr(q, "contents", []) or []],
        "choices": [
            {"number": getattr(c, "number", None),
             "contents": [_block_sig(b) for b in getattr(c, "contents", []) or []]}
            for c in getattr(q, "choices", []) or []
        ],
        "sub_questions": [_q_sig(s) for s in getattr(q, "sub_questions", []) or []],
    }
    for f in ("answer", "solution"):
        lines = getattr(q, f, None) or []
        sig[f] = [[_block_sig(b) for b in line] for line in lines]
    return sig


def _doc_sig(doc) -> list:
    return [_q_sig(q) for page in doc.pages for q in page.questions]


# ── 두 경로 ─────────────────────────────────────────────────────────────────
def _exe_document(envelope: dict):
    """배포 exe(GUI 워커) 경로."""
    from gui.main_window import ConversionWorker
    from core.content_parser import parse_ocr_response, build_document

    w = ConversionWorker.__new__(ConversionWorker)
    w.render_figures = False
    env = json.loads(json.dumps(envelope, ensure_ascii=False))   # 원본 보호
    w._resolve_figures(env, None, 1, 0)
    return build_document([parse_ocr_response(env, page_number=1)])


def _web_document(envelope: dict):
    """웹 경로 — HTTP JSON 2홉(JS 숫자 의미론) + 커넥터 figure 해소."""
    from server.convert_cli import resolve_figures
    from core.content_parser import parse_ocr_response, build_document

    env = _js_json_roundtrip(json.loads(json.dumps(envelope, ensure_ascii=False)))
    resolve_figures(env)
    return build_document([parse_ocr_response(env, page_number=1)])


def _diff(a, b, path="") -> list[str]:
    """두 시그니처의 차이를 사람이 읽는 경로로."""
    out: list[str] = []
    if type(a) is not type(b):
        return [f"{path}: 타입 {type(a).__name__} vs {type(b).__name__} ({a!r} / {b!r})"]
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                out.append(f"{path}.{k}: exe 없음 / web={b[k]!r}")
            elif k not in b:
                out.append(f"{path}.{k}: exe={a[k]!r} / web 없음")
            else:
                out += _diff(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append(f"{path}: 길이 {len(a)} vs {len(b)}")
        for i in range(min(len(a), len(b))):
            out += _diff(a[i], b[i], f"{path}[{i}]")
    elif a != b:
        out.append(f"{path}: exe={a!r} / web={b!r}")
    return out


def main(argv: list[str]) -> int:
    filters = [a for a in argv if not a.startswith("-")]
    corpus = ROOT / "corpus"
    entries = [d for d in sorted(corpus.iterdir())
               if (d / "ocr").is_dir()
               and (not filters or any(f in d.name for f in filters))]
    if not entries:
        print("대조할 corpus 가 없습니다.")
        return 2

    total_q = 0
    bad_entries: list[tuple[str, list[str]]] = []
    print(f"exe ↔ 웹 결과 대조 — corpus {len(entries)}편 (외부 API 0원)\n")

    for d in entries:
        qs = []
        for fp in sorted((d / "ocr").glob("p*_merged.json")):
            try:
                qs.extend(json.loads(fp.read_text(encoding="utf-8")).get("questions", []))
            except Exception as e:  # noqa: BLE001
                print(f"  [건너뜀] {d.name}/{fp.name}: {e}")
        if not qs:
            continue
        env = {"header": "", "questions": qs}
        try:
            a = _doc_sig(_exe_document(env))
            b = _doc_sig(_web_document(env))
        except Exception as e:  # noqa: BLE001
            bad_entries.append((d.name, [f"예외: {type(e).__name__}: {e}"]))
            print(f"  ERR  {d.name[:52]:54} {type(e).__name__}")
            continue
        total_q += len(a)
        diffs = _diff(a, b, "doc")
        if diffs:
            bad_entries.append((d.name, diffs))
            print(f"  DIFF {d.name[:52]:54} {len(diffs)}건")
        else:
            print(f"  OK   {d.name[:52]:54} 문항 {len(a)}")

    print()
    print(f"문항 {total_q}개 / 시험지 {len(entries)}편")
    if not bad_entries:
        print("✅ 전부 동일 — exe 와 웹이 같은 문서를 만든다")
        return 0

    print(f"❌ 차이 {len(bad_entries)}편\n")
    for name, diffs in bad_entries[:10]:
        print(f"[{name}]")
        for line in diffs[:12]:
            print(f"   {line}")
        if len(diffs) > 12:
            print(f"   … 외 {len(diffs) - 12}건")
        print()
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
