# 수식 크기 골든셋 기준 XML (삭제 금지)

조암중 수기 완성본(`data/[조암중][2][25-1-중간][동아강] (워드).hwp`)을 HWPX 로 변환해
**압축 해제**한 폴더. `Contents/section0.xml` 의 수식 84개 실측 (script, width, height)이
수식 크기 추정기의 **골든셋 기준**이다.

- 회귀: `tests/test_equation_metrics.py` (13 cases)
- 추출: `scripts/tune_equation/extract_golden.py`
- 재압축(유효 HWPX 복원): `scripts/tune_equation/repack_reference.py`
