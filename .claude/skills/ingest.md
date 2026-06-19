Ingest a document into the LLM-Wiki.

## Usage

```bash
python -m scripts.ingest raw/<파일명>
# 또는
poetry run ingest raw/<파일명>
```

## What it does

1. `raw/` 폴더의 PDF 또는 TXT 파일을 텍스트로 추출
2. LLM이 청크별로 개념/엔티티/요약을 분석
3. `wiki/sources/`, `wiki/concepts/`, `wiki/entities/`에 마크다운 페이지 생성
4. `wiki/index.md`에 새 페이지 목록 추가
5. `wiki/log.md`에 인제스트 이력 기록

## Example

```bash
python -m scripts.ingest "raw/자본시장과 금융투자업에 관한 법률(법률)(제21324호)(20260203).pdf"
```
