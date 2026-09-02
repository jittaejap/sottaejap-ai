# 소때잡 AI Server 온보딩

## 프로젝트 한 줄 설명

소때잡의 사용자 자연어를 이해하고 Spring 서비스 및 금융 RAG Tool을 조정해 자연어로 설명하는 FastAPI 기반 Single Agent 서버다.

## 전체 서비스 구조

```text
사용자 → Vue → Spring → FastAPI / Single Agent → Tool
                                              ├─ Spring API
                                              └─ Financial RAG
```

Vue는 사용자 화면, Spring은 데이터와 서비스 정책, FastAPI는 자연어 및 Tool 조정을 담당한다.

## Spring과 AI 역할 분리

```text
Spring = 데이터 / 규칙 / 계산 / 최종 판정
AI     = 자연어 / Agent / Tool / RAG / 설명
```

Spring은 거래와 회고 데이터, 목표, Baseline, Anomaly Score, 후보 선정, 반복 행동 분류, 만족도 보정, 절감액, 전월 대비 감소액, 목표 달성률 및 Rule Engine을 소유한다.

AI 서버는 Single Agent, 의도 파악, 회고 구조화, Tool Calling, 금융 RAG, 결과 조합 및 자연어 설명을 소유한다. Agent나 Tool에서 Spring의 결과를 다시 계산하거나 보정하면 안 된다.

## 처음 확인해야 할 파일

다음 순서로 읽는다.

1. [`README.md`](../README.md) — 전체 Architecture와 실행 방법
2. [`app/main.py`](../app/main.py) — FastAPI 앱 진입점
3. [`app/api/chat.py`](../app/api/chat.py) — Spring이 호출하는 `/chat`
4. [`app/agent/agent.py`](../app/agent/agent.py) — Single Agent 실행 경계
5. [`app/tools/README.md`](../app/tools/README.md) — Tool과 Spring 연동 원칙
6. [`app/reflection/README.md`](../app/reflection/README.md) — 회고 구조화 흐름
7. [`app/rag/README.md`](../app/rag/README.md) — 금융 RAG 경계
8. [`docs/DEVELOPMENT.md`](DEVELOPMENT.md) — 실제 기능 추가 규칙

## 기본 요청 흐름

```text
User Message
  ↓
POST /chat
  ↓
Single Agent
  ↓
Tool 선택
  ↓
Spring API 또는 RAG
  ↓
ToolResult
  ↓
Agent
  ↓
ChatResponse
```

Task 상태는 LLM이 기억하지 않는다. Spring이 `task_context`로 현재 Task, 상태, 구조화된 진행 상태를 전달하고, 필요할 때만 최소 최근 대화를 `recent_messages`로 전달한다. MVP에서는 사용자당 ACTIVE Task가 최대 하나라는 전제를 Spring이 관리한다.

## 반드시 지켜야 하는 경계

- Spring: 데이터, 규칙, 계산, 최종 판정
- AI: 자연어, Agent, Tool, RAG, 설명
- 외부 HTTP: `app/clients/spring_client.py`에서만 수행
- 금융 RAG 직접 호출: `financial_rag_tool.py`에서만 수행
- 알 수 없는 회고 값: 추측하지 않고 `None` 또는 `UNKNOWN`
- 확정되지 않은 Spring API: 임의 경로를 만들지 않고 TODO 유지

특히 Python에서 Baseline, Anomaly Score, Reflection Score, 반복 행동 최종 분류, 만족도 보정, 예상 절감액, 목표 달성률을 계산하지 않는다.

## 현재 개발 상태

완료:

- 실행 가능한 FastAPI 앱과 Health/Chat Endpoint
- Agent, Registry, SpringClient, Tool의 기본 호출 구조
- 회고 DTO 및 Extract/Normalize/Validate 구조
- 금융 Chunk/Embedding/Retriever 구조
- 외부 서비스 없는 단위 테스트

진행 예정:

- OpenAI Structured Output 및 Tool Calling
- Spring API 명세 협의와 Client 연결
- 금융 문서 및 pgVector 기반 검색

TODO는 코드의 `TODO`와 루트 README의 현재 구현 범위를 함께 확인한다.

## 작업 시작 방법

```text
Issue 확인
  ↓
main 최신화
  ↓
feature/* branch 생성
  ↓
개발 + 문서 수정
  ↓
pytest
  ↓
PR
```

기능을 추가하기 전에 소유 계층을 먼저 결정한다. 규칙이나 최종 분석값이라면 Python 구현을 시작하지 말고 Spring API 계약부터 협의한다.

