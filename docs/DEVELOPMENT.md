# 소때잡 AI Server 개발 규칙

## 1. 기본 개발 원칙

- Tool에 비즈니스 계산 로직을 넣지 않는다.
- Agent가 분석 값을 직접 계산하지 않는다.
- Spring에서 계산된 결과를 최종 분석값으로 사용한다.
- DB를 AI Agent가 임의로 직접 수정하지 않는다.
- Spring API가 확정되지 않은 경우 임의 Endpoint를 만들지 않는다.
- 요청 시 전달된 현재 Task Context를 사용하며 전체 채팅 History에 상태 관리를 맡기지 않는다.
- 불필요한 Framework, 추상화, 디자인 패턴을 도입하지 않는다.

## 2. 새로운 Tool 추가 방법

1. `app/tools`에 책임이 하나인 Tool을 만든다.
2. `app/schemas/tool.py` 또는 도메인 모듈에 Input/Output DTO를 정의한다.
3. 외부 데이터가 필요하면 `SpringClient`에 명명된 메서드를 추가한다.
4. Spring API 경로와 계약이 확정된 뒤에만 실제 HTTP 요청을 연결한다.
5. `ToolRegistry`에 Agent가 호출할 Handler를 등록한다.
6. Client 반환값을 그대로 전달하는지, 계산을 추가하지 않는지 테스트한다.
7. `app/tools/README.md`와 관련 문서를 갱신한다.

```text
Agent
  ↓
Tool
  ↓
SpringClient
  ↓
Spring API
```

금융 외부 지식만 `FinancialRagTool → app/rag` 흐름을 허용한다.

## 3. Spring API 연동 규칙

- HTTP 통신과 `httpx` 사용은 `app/clients/spring_client.py`에서 관리한다.
- Tool에서 URL, Header, Timeout을 직접 다루지 않는다.
- Timeout, Connection Error, 4xx/5xx를 구분해 상위 계층이 처리할 수 있어야 한다.
- Spring 응답 구조와 AI 내부 DTO를 명확히 분리한다.
- 경로, HTTP Method, Request/Response가 합의되기 전에는 `SpringEndpointNotConfiguredError`와 TODO를 유지한다.
- Client 수명주기를 관리하고 테스트에서는 `httpx.MockTransport` 또는 Fake Client를 사용한다.
- 인증 방식이 확정되면 공통 Client 수준에서 적용하고 Tool별로 복제하지 않는다.

## 4. Reflection 개발 규칙

```text
Natural Language
  ↓
Extract
  ↓
Normalize
  ↓
Validate
  ↓
필요 시 사용자 확인
  ↓
Spring API로 저장
```

- Extract는 문장에서 확인되는 후보만 반환한다.
- Normalize는 표기 차이를 표준 값으로 바꾸며 새로운 사실을 만들지 않는다.
- Validate는 미확정 필드와 추가 확인 필요 여부를 표시한다.
- 확정할 수 없는 값은 `None` 또는 `UNKNOWN`이다.
- AI 결과는 사용자에게 다시 보여주고 수정할 수 있는 DTO여야 한다.
- LLM Structured Output을 도입해도 Pydantic 검증을 생략하지 않는다.
- 만족도 보정과 Reflection Score 같은 서비스 계산은 Spring 소유다.

## 5. Agent 개발 규칙

Agent가 하는 일:

- 사용자 메시지와 현재 Task Context 확인
- 자연어 의도 파악과 Tool 선택
- Tool 결과 수집·조합
- 근거에 맞는 자연어 응답 생성

Agent가 하지 않는 일:

- Anomaly Score, Baseline, Reflection Score 계산
- 만족도 보정, 절감액, 목표 달성률 계산
- 반복 행동 최종 판정
- DB 직접 조회 또는 조작
- 전체 대화 기록을 영구 Task 상태로 사용

Tool Calling 구현 시 실행 횟수 제한, 알 수 없는 Tool, Tool 오류, 사용자 확인 필요 상태를 테스트한다. 프롬프트만으로 계층 경계를 보장하지 말고 코드 구조와 DTO로도 보장한다.

## 6. RAG 개발 규칙

MVP 흐름은 다음과 같다.

```text
문서 → Chunk → Embedding → pgVector
질문 → Query Embedding → Top-K Vector Search → 관련 Chunk → Agent
```

- Chunking, Embedding, Retrieval 책임을 분리한다.
- Retriever는 근거 본문, Source, Metadata, Score를 반환한다.
- 답변은 검색 근거 밖의 사실을 확정하지 않고 출처와 기준 시점을 유지한다.
- 금융 RAG는 개인화된 투자 권유가 아닌 정보 설명 용도다.
- 검색 로직을 한 파일이나 특정 Framework에 강하게 결합하지 않는다.

초기 범위에 Hybrid Search, Reranking, Query Expansion, Multi Query, Agentic RAG는 포함하지 않는다. 필요가 검증되면 Retriever 구현을 교체하는 방식으로 확장한다.

## 7. 코드 규칙

- Python 3.12+ 문법과 type hint를 사용한다.
- 외부 경계와 구조화 데이터에는 Pydantic DTO를 사용한다.
- 함수와 클래스의 책임을 작게 유지한다.
- 순환 참조를 만들지 않는다.
- 미확정 구현에는 이유가 드러나는 TODO를 남긴다.
- 핵심 파일에는 목적, 책임, 하지 않는 일을 짧은 module docstring으로 쓴다.
- 읽기 쉬운 코드에 한 줄씩 설명하는 주석은 달지 않는다.
- 필요한 현재 요구 이상으로 추상화하거나 디자인 패턴을 추가하지 않는다.

권장 의존 방향:

```text
api → agent → tools → clients
              └────→ rag (FinancialRagTool만)
reflection → schemas
core ← 외부 Client 구성
```

## 8. 테스트 기준

최소 테스트 범위:

- Agent가 기본 `ChatResponse` 계약을 지키는지
- 회고 DTO가 UNKNOWN/null을 허용하고 미확정 필드를 표시하는지
- Tool이 Spring Client 결과를 계산 없이 전달하는지
- RAG Retriever가 외부 DB 없이 인터페이스 계약을 지키는지
- `/health`, `/chat`이 실행 가능한지

실제 OpenAI API와 Spring API 호출은 기본 테스트에 포함하지 않는다. Fake, Stub, MockTransport를 사용한다. 버그 수정에는 재현 테스트를 먼저 추가한다.

```bash
pytest
```

## 9. Git 작업 규칙

```text
main
  ↓
feature/*
  ↓
PR
  ↓
Review
  ↓
Merge
```

- 기능, 테스트, 문서를 같은 PR에서 일관되게 갱신한다.
- 관련 없는 파일을 함께 정리하거나 덮어쓰지 않는다.
- 미확정 Spring 계약이나 서비스 정책을 구현으로 사실상 확정하지 않는다.
- PR에는 계층 경계 변경 여부와 남은 TODO를 명시한다.

