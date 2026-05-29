"""골든셋 수식에서 현재 폭 테이블에 등록되지 않은 토큰을 찾는다."""

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.hwpx_writer import (  # type: ignore
    _HWPEQ_CHAR_WIDTHS,
    _HWPEQ_KEYWORD_WIDTHS,
    _SYMBOL_KEYWORDS,
    _LARGE_OP_KEYWORDS,
    _STRUCT_KEYWORDS,
)

GOLDEN_JSON = Path(__file__).parent / "golden_equations.json"

KNOWN = (
    set(_SYMBOL_KEYWORDS) | set(_LARGE_OP_KEYWORDS) | set(_STRUCT_KEYWORDS)
)


def main() -> None:
    samples = json.loads(GOLDEN_JSON.read_text(encoding="utf-8"))

    # ── 알파벳 기반 "키워드스러운" 토큰 (2글자 이상) ──
    word_re = re.compile(r"\b[A-Za-z]{2,}\b")
    all_words: Counter = Counter()
    unknown_words: Counter = Counter()
    for s in samples:
        for w in word_re.findall(s["script"]):
            all_words[w] += 1
            if w not in KNOWN:
                unknown_words[w] += 1

    print("=== 골든셋에 쓰였지만 KNOWN 키워드 목록에 없는 토큰 ===")
    for w, n in unknown_words.most_common():
        print(f"  {w:20s}  {n}회")

    # ── 문자 단위 누락 (_HWPEQ_CHAR_WIDTHS 기준) ──
    # 단, 키워드에 속한 문자는 제외하고 "남은 문자"만 체크
    print("\n=== _HWPEQ_CHAR_WIDTHS에 없는 개별 문자 (키워드 토큰 제거 후) ===")
    unknown_chars: Counter = Counter()
    for s in samples:
        script = s["script"]
        # 키워드 + 구조 명령어 제거
        for kw in sorted(KNOWN, key=len, reverse=True):
            script = script.replace(kw, " ")
        for ch in script:
            if ch in "{}\\ \n\t":
                continue
            if ch in _HWPEQ_CHAR_WIDTHS:
                continue
            unknown_chars[ch] += 1

    for ch, n in unknown_chars.most_common():
        # 한글/한자/따옴표 등
        category = (
            "한글"
            if "가" <= ch <= "힣"
            else "한글자모" if "ㄱ" <= ch <= "ㆎ"
            else "기호"
        )
        print(f"  {ch!r:8s} ({category})  {n}회  (코드 U+{ord(ch):04X})")


if __name__ == "__main__":
    main()
