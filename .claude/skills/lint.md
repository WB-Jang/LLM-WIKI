Check LLM-Wiki health.

## Usage

```bash
python -m scripts.lint
# 또는
poetry run lint
```

## What it checks

- **깨진 링크**: 존재하지 않는 페이지를 가리키는 `[[wikilink]]`
- **고아 페이지**: 어느 페이지에서도 참조되지 않는 페이지

## Output example

```
📊 위키 건강성 검사
   전체 페이지: 42개
   깨진 링크: 2개
     ❌ concepts/공모펀드.md → [[투자회사법]]
   고아 페이지: 1개
     ⚠️  synthesis/overview.md
```
