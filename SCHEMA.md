# LLM-Wiki 스키마

## 디렉토리 구조

```
wiki/
├── index.md          # 전체 페이지 카탈로그 (자동 업데이트)
├── log.md            # append-only 변경 이력 (자동 추가)
├── sources/          # 원문 요약 페이지
├── concepts/         # 개념 페이지
├── entities/         # 엔티티 페이지 (기관, 제도, 인물 등)
└── synthesis/        # 여러 소스 교차 분석 종합 페이지 (수동 작성)

raw/                  # 원본 입력 문서 (PDF, TXT)
```

## 페이지 타입별 프론트매터

### source
```yaml
---
type: source
title: 페이지 제목
date_ingested: YYYY-MM-DD
tags: []
---
```

### concept
```yaml
---
type: concept
title: 개념명
sources: [[출처페이지]]
tags: []
---
```

### entity
```yaml
---
type: entity
entity_type: 기관|법령|제도|지표|인물
title: 엔티티명
sources: [[출처페이지]]
tags: []
---
```

### synthesis
```yaml
---
type: synthesis
title: 종합 분석 제목
sources: [[출처1]], [[출처2]]
date_created: YYYY-MM-DD
tags: []
---
```

## 크로스 레퍼런스 규칙

- 다른 위키 페이지 참조 시 `[[페이지명]]` 형태 사용
- 파일명(`_slugify` 결과)이 아닌 **페이지 제목**으로 링크
- 개념과 엔티티는 첫 등장 시 반드시 링크 처리

## log.md 액션 종류

| 액션 | 의미 |
|------|------|
| INGEST | 새 문서 인제스트 |
| UPDATE | 기존 페이지 수동 업데이트 |
| LINT | 건강성 검사 결과 |
| SYNTHESIS | 종합 분석 페이지 생성 |
