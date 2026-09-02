# Financial RAG 모듈

## 목적

금융 일반 지식이 필요한 질문에 근거가 되는 문서 Chunk를 검색한다. 거래·회고·개인 분석 데이터는 금융 RAG 대상이 아니며 Spring Tool을 사용한다.

## MVP 구조

문서 적재:

```text
금융 문서 → 텍스트 추출 → Chunking → Embedding → pgVector
```

질문 검색:

```text
사용자 질문 → Query Embedding → Top-K Vector Search → 관련 Chunk → Agent
```

## 구성요소

- `chunker.py`: 단순 문자 수 기반 중첩 Chunking
- `embedding.py`: Provider에 결합되지 않은 Embedding 경계
- `retriever.py`: pgVector 구현으로 교체할 검색 인터페이스
- `prompt.py`: 검색 근거 안에서 답변하도록 하는 금융 응답 지침
- `schemas.py`: Source와 Metadata를 보존하는 Chunk/SearchResult DTO
- `scripts/ingest_financial_docs.py`: 문서 적재 파이프라인 진입점

현재 Retriever는 외부 DB 없이 빈 목록을 반환한다. 실제 금융 문서, Embedding Provider, pgVector 스키마와 Top-K 검색은 TODO다.

## 확장 방향

MVP에서는 단순 Vector Search를 사용한다. Hybrid Search, Reranking, Query Expansion, Multi Query, Agentic RAG는 초기 범위가 아니다. 향후 품질 측정 결과 필요할 때 `FinancialRetriever` 구현을 교체하되 Agent와 Tool 계약은 유지한다.

검색 결과는 근거 본문, Source, 기준 시점 Metadata를 잃지 않아야 한다. 답변은 개인화된 투자 권유가 아니라 근거 기반 정보 설명으로 제한한다.

