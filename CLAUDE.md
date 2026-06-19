# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---


## 5. No Libraries installed locally
If it needs, write dockerfile, docker-compose, pyproject.toml, devcontainer.json and build up vm with any necessary libraries using poetry

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

---

## LLM-Wiki 운영 지침

이 프로젝트는 Karpathy의 LLM-Wiki 패턴을 구현합니다. RAG(검색 증강)가 아니라 **LLM이 직접 위키를 읽고 유지합니다.**

### 아키텍처

```
raw/ (원본 문서) → ingest → wiki/ (마크다운 페이지) → query → 답변
```

### 핵심 원칙

- `raw/`의 원본 문서는 **절대 수정하지 않음**
- `wiki/log.md`는 **append-only** — 기존 내용 삭제 금지
- `wiki/index.md`는 전체 페이지 카탈로그 — 인제스트 시 자동 업데이트
- 위키 페이지 간 참조는 반드시 `[[페이지명]]` 형태 사용

### 주요 명령어

| 명령 | 설명 |
|------|------|
| `python -m scripts.ingest raw/<파일>` | 문서 → 위키 페이지 생성 |
| `python -m scripts.query "질문"` | 위키 읽어서 답변 |
| `python -m scripts.lint` | 깨진 링크 / 고아 페이지 검사 |
| `python -m app.web` | NiceGUI 웹 인터페이스 실행 |

### 위키 페이지 편집 시

- 기존 `[[wikilink]]`를 깨지 않도록 주의
- 프론트매터 형식은 `SCHEMA.md` 참고
- 편집 후 `lint`로 링크 검증
