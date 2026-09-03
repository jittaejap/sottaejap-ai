# Tools 모듈

## 역할

Tool은 Agent의 의도를 실제 데이터 또는 검색 기능에 연결하는 얇은 Wrapper다. Tool 내부에서 비즈니스 계산이나 최종 판정을 수행하지 않는다.

```text
Agent → Tool → SpringClient → Spring API
Agent → FinancialRagTool → FinancialRetriever
```

## Tool 목록

| Tool | 책임 |
|---|---|
| `TransactionTool` | Spring 거래 데이터 조회 |
| `ReflectionTool` | 구조화된 회고 조회·저장 |
| `AnalysisTool` | Spring Rule Engine의 소비 분석 결과 조회 |
| `ActionPlanTool` | Spring이 계산한 행동 조정·예상 절감 결과 조회 |
| `MemoryTool` | 저장 방식과 분리된 개인 소비 메모리 조회 |
| `FinancialRagTool` | Python 내부 금융 RAG 검색 |

## Spring API Wrapper 원칙

- Tool은 `httpx`, URL, 인증 Header를 직접 다루지 않는다.
- 모든 Spring HTTP 호출은 `app/clients/spring_client.py`에 둔다.
- Spring 응답에 Python 계산을 덧붙이지 않는다.
- 경로는 `sottaejap-docs/05_API_명세서.md` §3 표가 정본이다. 문서에 없는 경로를 만들지 않는다.
- `SpringClient`는 봉투를 벗긴 `data`(camelCase)를 돌려준다. Tool은 그것을 그대로 `ToolResult.data`에 넣는다.
- `FinancialRagTool`만 `app/rag`를 직접 호출할 수 있다.

## 금지되는 비즈니스 로직

Baseline, Anomaly Score, Reflection Score, 만족도 보정, 예상 절감액, 목표 달성률, 반복 행동 최종 분류는 Tool에서 구현하지 않는다. 이 값은 Spring의 최종 결과를 사용한다.

## 새로운 Tool 추가 방법

1. `app/tools`에 한 책임의 Tool 파일을 만든다.
2. Input/Output Pydantic Schema를 정의한다.
3. 필요한 `SpringClient` 메서드를 추가한다.
4. 05 §3에 있는 API 계약만 HTTP 호출로 구현한다.
5. `ToolRegistry`에 Handler를 등록한다.
6. Fake Client로 위임 동작을 테스트한다.
7. 이 문서의 Tool 목록을 갱신한다.

