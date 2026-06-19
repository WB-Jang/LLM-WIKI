# LLM-Wiki

PDF, TXT 등 문서를 LLM이 읽고 **마크다운 위키**로 변환·유지하는 지식 관리 시스템입니다.

[Andrej Karpathy의 LLM-Wiki 패턴](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)과 [claude-obsidian](https://github.com/AgriciDaniel/claude-obsidian)을 참조해 구현했습니다.

---

## RAG와의 차이점

| | 기존 RAG | LLM-Wiki |
|--|---------|---------|
| 지식 저장 방식 | 벡터 DB (임베딩) | 마크다운 파일 |
| 쿼리 방식 | 유사도 검색 → LLM 답변 | LLM이 위키 파일 직접 읽고 답변 |
| 지식의 형태 | 원문 청크 조각 | LLM이 정제·합성한 위키 페이지 |
| 지식 누적 방식 | 청크 추가 | 위키 페이지가 업데이트되며 **복리 성장** |
| 교차 참조 | 없음 | `[[wikilink]]`로 개념 간 연결 |
| 사람이 읽을 수 있나? | 어려움 | ✅ Obsidian에서 바로 열람 가능 |

**핵심 철학:** 위키는 한번 만들면 끝이 아니라 문서가 추가될수록 개념 간 연결이 늘고 지식이 심화되는 **누적 아티팩트**입니다.

---

## 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                         raw/                                │
│   (원본 PDF, TXT — 절대 수정하지 않음)                        │
└───────────────────────┬─────────────────────────────────────┘
                        │  scripts/ingest.py
                        │  (1) 텍스트 추출 (pdfplumber)
                        │  (2) 청크 분할 → LLM 분석
                        │  (3) 마크다운 페이지 생성
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                        wiki/                                │
│  ├── index.md        전체 페이지 카탈로그                     │
│  ├── log.md          append-only 변경 이력                   │
│  ├── sources/        원문 요약 페이지                         │
│  ├── concepts/       개념 페이지 (공모펀드, 투자매매업 등)      │
│  ├── entities/       엔티티 페이지 (금융위원회, 자본시장법 등)  │
│  └── synthesis/      수동 작성 교차 분석 페이지               │
└───────────────────────┬─────────────────────────────────────┘
                        │  scripts/query.py
                        │  (1) index.md로 페이지 목록 파악
                        │  (2) LLM이 관련 페이지 선택
                        │  (3) 페이지 읽고 답변 합성
                        ▼
                     답변 + [[출처 인용]]
```

---

## 디렉토리 구조

```
LLM-WIKI/
├── raw/                    원본 문서 (PDF, TXT)
├── wiki/                   Obsidian Vault — LLM이 생성·유지하는 위키
│   ├── index.md            전체 페이지 카탈로그 (자동 업데이트)
│   ├── log.md              변경 이력 (append-only)
│   ├── sources/            문서별 요약 페이지
│   ├── concepts/           개념 페이지
│   ├── entities/           엔티티 페이지
│   └── synthesis/          교차 분석 종합 페이지 (수동)
├── scripts/
│   ├── config.py           설정 로더, OpenRouter 클라이언트
│   ├── ingest.py           문서 → 위키 페이지 변환
│   ├── query.py            위키 기반 질문 답변
│   └── lint.py             위키 건강성 검사
├── app/
│   └── web.py              NiceGUI 웹 인터페이스
├── .claude/skills/         Claude Code 스킬
│   ├── ingest.md
│   ├── query.md
│   └── lint.md
├── SCHEMA.md               위키 구조 규칙 및 페이지 템플릿
├── config.yaml             LLM 모델, 앱 포트 설정
├── pyproject.toml          Python 의존성 (Poetry)
├── Dockerfile
└── docker-compose.yml
```

---

## 작동 원리

### 1. Ingest — 문서를 위키로 변환

`scripts/ingest.py`가 수행하는 단계:

```
PDF 파일
  └─→ pdfplumber로 텍스트 추출
        └─→ 10,000자 단위 청크 분할 (최대 10개)
              └─→ 각 청크마다 LLM 호출:
                    [요약] 2-3문장
                    [핵심개념] 개념1, 개념2, ...
                    [주요엔티티] 이름|타입, ...
                  └─→ 중복 제거 후 합산
                        └─→ LLM으로 페이지 생성:
                              wiki/sources/<문서명>.md    (소스 요약)
                              wiki/concepts/<개념명>.md   (개념별 페이지)
                              wiki/entities/<엔티티명>.md (엔티티별 페이지)
                            └─→ wiki/index.md 업데이트
                                  wiki/log.md에 이력 추가
```

**이미 존재하는 개념/엔티티 페이지는 덮어쓰지 않습니다.** 새 문서를 인제스트해도 기존 지식은 보존됩니다. 필요하면 소스 페이지에서 `[[기존개념]]`으로 자동 연결됩니다.

### 2. Query — 위키를 읽어 답변

`scripts/query.py`가 수행하는 단계:

```
질문
  └─→ wiki/ 전체 페이지 목록 + 미리보기 수집
        └─→ LLM이 관련성 높은 페이지 번호 선택 (최대 5개)
              └─→ 해당 마크다운 파일 읽기
                    └─→ LLM이 위키 내용 기반으로 답변 합성
                          └─→ [[페이지명]] 형태로 출처 인용
```

벡터 임베딩 없음 — LLM의 문맥 이해로 관련 페이지를 선택하고 답변합니다.

### 3. Lint — 위키 건강성 검사

`scripts/lint.py`가 확인하는 항목:

- **깨진 링크**: `[[페이지명]]`을 참조하지만 해당 마크다운 파일이 없는 경우
- **고아 페이지**: 어느 페이지에서도 참조되지 않는 파일

### 4. 위키 페이지 형식

모든 위키 페이지는 Obsidian 호환 마크다운으로 생성됩니다.

**소스 페이지** (`wiki/sources/`)
```markdown
---
type: source
title: 자본시장과 금융투자업에 관한 법률
date_ingested: 2026-06-19
tags: [금융법규]
---

# 자본시장과 금융투자업에 관한 법률

## 개요
투자자 보호와 금융투자업의 건전한 발전을 위한 법률입니다.

## 핵심 개념
- [[공모펀드]]
- [[투자매매업]]
- [[집합투자]]

## 주요 기관 및 제도
- [[금융위원회]] (기관)
- [[금융감독원]] (기관)

## 주요 내용
- 금융투자상품의 정의와 분류
- 투자매매업·투자중개업 인가 요건
...
```

**개념 페이지** (`wiki/concepts/`)
```markdown
---
type: concept
title: 공모펀드
sources: [[자본시장과 금융투자업에 관한 법률]]
tags: []
---

# 공모펀드

## 정의
50인 이상의 불특정 다수를 대상으로 자금을 모집하는 펀드.

## 상세 설명
...

## 관련 개념
- [[집합투자]]
- [[투자신탁]]

## 출처
- [[자본시장과 금융투자업에 관한 법률]]
```

---

## 설치 및 실행

### 사전 준비

1. `.env` 파일 생성:
   ```
   OPENROUTER_API_KEY=sk-or-v1-...
   ```
   [OpenRouter](https://openrouter.ai)에서 API 키를 발급받습니다.

2. `config.yaml`에서 모델 선택 (기본값: `openai/gpt-4o`):
   ```yaml
   llm:
     model: openai/gpt-4o   # 또는 anthropic/claude-3.5-sonnet 등
   ```

### Docker (권장)

```bash
docker-compose up
```

브라우저에서 `http://localhost:8080` 접속.

### 로컬 (Poetry)

```bash
poetry install
poetry run wiki          # 웹 UI 실행
```

---

## 사용법

### 웹 인터페이스 (`http://localhost:8080`)

```
┌─────────────────────────────────────────────────────┐
│  LLM-Wiki                                           │
├──────────────┬──────────────────────────────────────┤
│ 📁 위키       │  [위키 페이지 뷰어]                   │
│  ├ 📄 index  │  # 자본시장과 금융투자업에 관한 법률   │
│  ├ 📄 log    │                                      │
│  ├ 📁 sources│  ## 개요                             │
│  ├ 📁 concepts  투자자 보호와...                     │
│  └ 📁 entities                                     │
│              │  ## 핵심 개념                        │
│ [📥 문서 추가]│  - [[공모펀드]]                      │
│              │──────────────────────────────────────│
│ [Lint] [새로  │  💬 질문하기                         │
│  고침]        │  ❓ 공모펀드의 정의는?               │
│              │  공모펀드란 50인 이상...               │
│              │  참고: 공모펀드, 자본시장법           │
│              │  [질문 입력창] [전송]                 │
└──────────────┴──────────────────────────────────────┘
```

- **왼쪽 사이드바**: 위키 트리 탐색, PDF 업로드, Lint 실행
- **오른쪽 상단**: 선택한 위키 페이지 마크다운 렌더링
- **오른쪽 하단**: 채팅 형태 질문 — LLM이 위키를 읽고 `[[출처]]` 인용하며 답변

### CLI

```bash
# 문서 인제스트
python -m scripts.ingest raw/자본시장법.pdf

# 질문
python -m scripts.query "공모펀드와 사모펀드의 차이는?"

# 위키 건강성 검사
python -m scripts.lint
```

### Claude Code 스킬

Claude Code CLI에서 `/ingest`, `/query`, `/lint` 스킬로 실행 가능합니다. (`.claude/skills/` 참고)

---

## 설정 (`config.yaml`)

```yaml
llm:
  provider: openrouter
  base_url: https://openrouter.ai/api/v1
  model: openai/gpt-4o      # 사용할 LLM 모델
  temperature: 0.1
  max_tokens: 4096

wiki:
  dir: wiki                 # 위키 마크다운 저장 경로
  raw_dir: raw              # 원본 문서 경로

app:
  title: "LLM-Wiki"
  port: 8080
```

### 지원 모델 (OpenRouter)

| 모델 ID | 특징 |
|---------|------|
| `openai/gpt-4o` | 기본값, 균형 잡힌 성능 |
| `anthropic/claude-3.5-sonnet` | 긴 문서 처리에 강점 |
| `google/gemini-flash-1.5` | 빠른 처리 속도 |
| `meta-llama/llama-3.3-70b-instruct` | 오픈소스 |
| `deepseek/deepseek-chat` | 비용 효율 |

---

## Obsidian 연동

`wiki/` 폴더를 Obsidian에서 Vault로 열면:

- `[[wikilink]]` 자동 하이퍼링크 렌더링
- 그래프 뷰에서 개념 간 연결 시각화
- YAML 프론트매터로 페이지 타입 필터링
- 문서가 쌓일수록 지식 그래프가 조밀해지는 것을 시각적으로 확인 가능

---

## 의존성

| 라이브러리 | 역할 |
|-----------|------|
| `nicegui` | 웹 인터페이스 |
| `openai` | OpenRouter API 클라이언트 |
| `pdfplumber` | PDF 텍스트 추출 |
| `pyyaml` | config.yaml 파싱 |
| `python-dotenv` | `.env` 로드 |

벡터 DB, 임베딩 모델, LangChain 등의 무거운 의존성이 없습니다.
