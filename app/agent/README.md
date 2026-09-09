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
HANDLERS에서 Task Handler 조회
  ├─ 등록됨: HandlerContext로 Handler 실행
  └─ 미등록: 기존 LLM 1회 생성
  ↓
ChatResponse
```

`HANDLERS`에는 현재 `TaskType.CLUSTER_NAMING`(#29)과 `TaskType.FINANCE_QA`(#21)가 등록돼 있다. `SingleAgent.run()`은 ACTIVE Task에 등록된 Handler가 있으면 실행하고, 없으면 시스템 프롬프트에 현재 작업과 `state`를 붙여 기존처럼 LLM을 1회 호출한다. COMPLETED Task는 Handler를 실행하지 않는다. `LLMUnavailableError`(6초 초과 · 재시도 1회 실패)나 `LLMNotConfiguredError`(키 없음)는 `SingleAgent.run()` 한 곳에서 `app/ai/fallback.py` 템플릿과 `fallback=True` 응답으로 전환한다. OpenAI Tool Calling 실행 루프와 나머지 Task(REFLECTION·ACTION_PLAN·ANALYSIS·ANALYSIS_NARRATE)의 Handler는 TODO다. 별도 Agent Framework는 필요가 검증되기 전 도입하지 않는다.

## 파일 책임

- `agent.py`: Single Agent 조정 진입점
- `handlers/base.py`: Handler가 공유하는 LLM·Tool 실행 Context와 응답용 Tool 영수증
- `handlers/__init__.py`: Task별 Handler를 연결하는 `HANDLERS` 레지스트리
- `handlers/cluster_naming.py`: `TaskType.CLUSTER_NAMING` — Spring이 전달한 묶음 정보로 12자 이내 이름을 만든다
- `handlers/finance_qa.py`: `TaskType.FINANCE_QA` — `FINANCIAL_RAG` Tool로 근거를 찾아 그 안에서만 답하고, 없으면 모른다고 답한다
- `prompt.py`: 시스템 및 Agent 프롬프트
- `state.py`: 요청 한 건에 필요한 현재 Task, 구조화 상태, 최소 최근 대화
- `tool_registry.py`: Agent에 노출할 Tool 이름과 Handler 등록·조회, Spring pull Tool 5종 기본 배선(`build_default_registry`)

Registry는 `app/main.py` lifespan이 만든다. `build_default_registry()`가 Spring pull Tool 5종(`transaction` · `reflection` · `analysis` · `action_plan` · `memory`)을 등록하고, `FINANCIAL_RAG`는 `DATABASE_URL`이 있을 때만 덧붙인다. 회고 저장은 05 §3 v2.2 본문과 `ReflectionExtraction`이 어긋나 있어 아직 등록하지 않는다 (#10). 등록되지 않은 Tool을 불러도 `HandlerContext.call_tool`이 `success=False`로 바꾼다.

`state.py`는 영구 저장소가 아니다. 실제 ACTIVE/PAUSED/COMPLETED Task와 사용자별 진행 상태는 Spring/DB가 소유한다.

`recent_messages`는 05 §2·§3의 E-87 계약에 따라 오래된 발화부터 최신 발화 순으로 담는다. `last_question`은
가장 최근 assistant 발화의 문장 맥락을 제공할 뿐이며, REFLECTION 단계 판정은 `task_context.state.step`을 기준으로 한다.

## 새로운 Handler 추가 방법

1. `app/agent/handlers`에 하나의 `TaskType`만 담당하는 async Handler를 만든다.
2. Handler는 `HandlerContext.generate()`와 `call_tool()`을 사용하고 `ChatResponse`를 반환한다.
3. `LLMNotConfiguredError`와 `LLMUnavailableError`는 Handler에서 잡지 않는다. 중앙 폴백은 `SingleAgent.run()`이 담당한다.
4. Tool 결과를 응답에 실을 때 `tool_receipt()`를 사용한다. 단, 05 §3 계약에 따라 `reflection` 결과의 `data`는 Spring이 읽을 수 있도록 보존된다.
5. `handlers/__init__.py`의 `HANDLERS`에 해당 `TaskType`과 Handler를 등록한다.
6. 등록된 Handler 실행, COMPLETED 우회, Tool 실패 및 LLM 폴백 경계를 테스트한다.

Handler는 계산이나 최종 판정을 하지 않는다. 필요한 데이터는 Tool을 통해 Spring에서 받고, 정본 계약에 없는 API나 DTO가 필요하면 문서를 먼저 변경한다.
