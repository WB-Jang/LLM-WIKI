Query the LLM-Wiki.

## Usage

```bash
python -m scripts.query "질문 내용"
# 또는
poetry run query "질문 내용"
```

## What it does

1. `wiki/` 전체 페이지 목록 파악
2. LLM이 질문과 관련성 높은 페이지 선택 (최대 5개)
3. 선택된 위키 페이지를 직접 읽어 답변 합성
4. `[[페이지명]]` 형태로 출처 인용

벡터 DB 없음 — LLM이 위키 마크다운을 직접 읽어 답변합니다.

## Example

```bash
python -m scripts.query "자본시장법에서 공모펀드의 정의는?"
```
