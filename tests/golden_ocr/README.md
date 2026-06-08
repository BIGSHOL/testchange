# 골든셋 (ground-truth OCR JSON)

이 디렉터리의 `*.json` 은 **정답 OCR 결과**(사람이 크롭 PNG 를 보고 교정)다. **commit 대상**
(텍스트라 작고 가치의 80%). 프롬프트를 바꿀 때마다 같은 크롭셋에 대해 모델 출력 ↔ 이 정답을
자동 채점해 성능 회귀를 잡는다(플라이휠). 채점기는 `scripts/ocr_eval/`(stdlib only).

## 파일 스키마 (`<sample_id>.json`)
```json
{
  "schema_version": 1,
  "sample_id": "<pdf_stem>__p<i>__c<ci>",
  "png_sha256": "<크롭 PNG sha256>",
  "source": {"pdf_stem": "...", "i": 0, "ci": 2, "bbox": [x0, y0, x1, y1]},
  "golden": {
    "header": "",
    "questions": [ { "number": 12, "score": 4, "contents": [...], "choices": [...], "sub_questions": [] } ]
  }
}
```
`golden` 본문은 `core/ocr_engine.py` 의 OCR 출력 스키마와 **동일**(`recognize_crop` 가 내는 것).
블록 타입: `text` · `equation` · `equation_block` · `figure` · `table`(`rows`).

## ⚠️ figure 작성 규칙 (채점 정확도에 직결)
- 그림은 **`{"type": "figure", "value": "<설명>"}` 블록으로만** 작성한다.
- testkit/배포 경로는 그림을 안내문(`※ 그림 자리 …`) text 로 치환하지만, **골든에는 절대 그
  안내문 text 를 넣지 말 것.** 채점기는 `type=="figure"` 일 때만 figure 로 인정하므로, 안내문
  text 를 넣으면 figure 존재 F1 이 틀어진다.

## 시딩 워크플로우 (사용자 PC — Gemini/Claude 키 필요)
```
1) python scripts/crop_dump.py "<PDF>"
     → .testkit/ocr_cache/<stem>/crops_png/crop_p{i}_c{ci}.png + crops_manifest.json
2) 각 크롭 PNG 를 보고 정답 JSON(위 golden 본문)을 작성 → 임시 파일로 저장
3) python scripts/ocr_eval/golden_record.py \
       --manifest .testkit/ocr_cache/<stem>/crops_manifest.json \
       --sample-id <stem>__p<i>__c<ci> \
       --golden-json <작성한.json>
     → 검증(sha256·스키마) 후 tests/golden_ocr/<sample_id>.json 기록
4) python scripts/ocr_eval/score_ocr.py "<PDF>"   # 현 프롬프트 vs 골든 채점
5) python tests/test_ocr_golden.py                # 회귀 게이트
```

## 시드 다양성 (중요)
텍스트 위주만 모으지 말 것. **표 포함 문항**(확률분포표·정규분포표)·**수식 비중 압도적 확통
문항**·**보기/조건 박스 문항**을 의도적으로 섞어, 각 회귀 태그(`TABLE_MISSING`·
`EQUATION_DRIFT`·`BOX_PROSE_DROP` 등)가 최소 한 샘플로 커버되게 한다.
