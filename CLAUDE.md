## Skills

커스텀 검증 및 유지보수 스킬은 `.claude/skills/`에 정의되어 있습니다.

| Skill | Purpose |
|-------|---------|
| `verify-implementation` | 프로젝트의 모든 verify 스킬을 순차 실행하여 통합 검증 보고서를 생성합니다 |
| `manage-skills` | 세션 변경사항을 분석하고, 검증 스킬을 생성/업데이트하며, CLAUDE.md를 관리합니다 |
| `verify-latex-hwpeq` | LaTeX→HWP 수식 변환 매핑 무결성 검증 |
| `verify-hwpx-structure` | HWPX 문서 생성 구조 검증 |
| `verify-equation-metrics` | 수식 크기 추정기 정확도 회귀 검증 (골든셋 84개 기반) |
| `verify-ocr-parser-sync` | OCR 엔진↔콘텐츠 파서 동기화 검증 |

## 작업 마무리 워크플로우 (필수)

코드를 변경한 뒤에는 **항상 아래 순서로 마무리**한다:

1. **검증** — 변경을 실데이터/렌더로 확인(가능하면 HWP COM 렌더 PNG로 육안 확인).
2. **사용자 최종 체크** — 커밋·푸시·배포 전에 **반드시 사용자에게 결과를 보여주고 확인(체크)을 받는다.** 사용자 승인 없이 커밋/푸시/배포하지 않는다.
3. **커밋 + 푸시** — 승인되면 커밋하고 **`testchange` 원격(BIGSHOL)** 으로 푸시한다 (`git push testchange master`).
4. **exe 빌드 + 배포** — `python -m PyInstaller build.spec --noconfirm` 로 재빌드하고, `dist/시험지한글화/` 의 exe와 `_internal` 을 `배포용/` 으로 복사한다. **`배포용/config.json` 은 보존**(robocopy `/MIR` 는 `_internal` 에만 적용). 배포 후 `--selftest` 로 임포트 확인.

### 보안 (절대 준수)
- **API 키(ANTHROPIC/GEMINI)는 gitignore된 `config.json` 에만** 둔다. 추적 파일·커밋에 키를 절대 넣지 않는다. (`config.json`, `build/`, `dist/`, `배포용/` 은 `.gitignore` 처리됨.)
