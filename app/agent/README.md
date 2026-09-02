# Agent 모듈

## 역할

`app/agent`는 한 번의 사용자 요청에서 현재 Context를 확인하고, 필요한 Tool을 선택하고, 결과를 조합해 자연어 응답을 만드는 Single Agent 영역이다.

담당 기능:

- 사용자 메시지와 Spring이 전달한 현재 Task 확인
- 자연어 의도 파악
- Tool 선택 및 호출 결과 수집
- 최종 자연어 설명 생성

담당하지 않는 기능:

- DB 직접 접근
- Baseline, Anomaly Score, Reflection Score 계산
- 만족도 및 절감액 계산
- 반복 행동 최종 판정
- 영구 Task 상태 관리

## Tool Calling Flow

```text
ChatRequest
  ↓
AgentState
  ↓
SingleAgent
  ↓
ToolRegistry에서 Tool 선택
  ↓
ToolResult 수집
  ↓
ChatResponse
```

초기 `SingleAgent.run()`은 실행 가능한 응답 계약만 제공한다. OpenAI Tool Calling 실행 루프와 결과 기반 답변 생성은 TODO다. 별도 Agent Framework는 필요가 검증되기 전 도입하지 않는다.

## 파일 책임

- `agent.py`: Single Agent 조정 진입점
- `prompt.py`: 시스템 및 Agent 프롬프트
- `state.py`: 요청 한 건에 필요한 현재 Task, 구조화 상태, 최소 최근 대화
- `tool_registry.py`: Agent에 노출할 Tool 이름과 Handler 등록·조회

`state.py`는 영구 저장소가 아니다. 실제 ACTIVE/PAUSED/COMPLETED Task와 사용자별 진행 상태는 Spring/DB가 소유한다.

