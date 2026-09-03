# 소때잡 AI Server

소때잡의 자연어 소비 회고, Tool Calling, 금융 지식 검색을 담당하는 Python/FastAPI 서버다. 이 저장소를 받으면 `POST /chat`을 로컬에서 띄우고, Spring `sottaejap-server`와 공유 시크릿으로 연결하고, 기능을 안전하게 추가할 수 있다.

코딩 에이전트(Claude Code · Codex)와 함께 작업한다면 [AGENTS.md](AGENTS.md)를 먼저 읽는다. 브랜치·커밋·PR 규칙은 [CONTRIBUTING.md](CONTRIBUTING.md)에 있다. 계약의 정본은 문서 저장소 [`sottaejap-docs`](https://github.com/jittaejap/sottaejap-docs)의 `01_결정로그.md`·`05_API_명세서.md` §3·`07_기술스택_레포구성.md`다.

## AI 서버 역할

AI 서버는 다음 작업을 조정한다.

- Single Agent 실행과 사용자 자연어 의도 파악
- 현재 Task Context를 이용한 Tool 선택
- 사용자 회고의 후보 값 구조화와 사용자 확인 요청 (표준 태그 7종 · 6종만 제안)
- Tool 결과 조합 및 자연어 설명 — 묶음 이름 짓기(⑤) · 회고 대화(⑥) · 소비 분석 문장화(⑨)
- 금융 질문을 위한 내부 RAG 호출 (P2)
- Spring 서비스와의 HTTP 통신
- LLM 장애 시 템플릿 응답으로 대체 (`fallback: true`)

데이터 영속화, 서비스 규칙, 수치 계산, 최종 판정은 AI 서버의 책임이 아니다.

## Spring과 AI 역할 분리

| Spring | Python AI Server |
|---|---|
| 거래·회고·목표 데이터 관리 | Single Agent와 자연어 이해 |
| 개인 Baseline 및 Anomaly Score 계산 | 자연어 회고 구조화 |
| 후보 선정, 반복 행동 최종 분류, `reason_code` 산출 | Tool 선택과 결과 조합 |
| 만족도 보정, 절감액·감소액·달성률 계산 | 금융 RAG와 자연어 설명 |
| Rule Engine과 최종 데이터·판정(`verdict`) | Spring API 통신, LLM 폴백 |

핵심 원칙은 다음과 같다.

```text
Spring = 데이터 / 규칙 / 계산 / 최종 판정
Python = Agent / 자연어 / Tool Calling / RAG / 설명
```

`analysis_tool`도 분석 알고리즘을 구현하지 않는다. 호출 흐름은 `Agent → analysis_tool → SpringClient → Spring Analysis API → Rule Engine`이다.

## 전체 Architecture

```text
사용자
  ↓
Vue (sottaejap-client)
  ↓
Spring (sottaejap-server) ── AiClient ──► POST /chat  (snake_case · X-Internal-Secret)
                                              ↓
                                     FastAPI / Single Agent
                                              ↓
                                            Tool
                    ├─ 거래·회고·분석·행동 제안·메모리 → SpringClient → Spring /internal/ai/users/{userId}/*  (X-Internal-Secret)
                    └─ 금융 지식 → Python Financial RAG → pgvector (P2 · TODO)
```

Spring이 AI를 부르는 경로는 `POST /chat` 하나다. AI가 데이터가 필요하면 Spring 내부 AI API 6종을 다시 부른다(pull). 두 방향 모두 같은 공유 시크릿으로 인증한다.

## 요청 흐름

```text
ChatRequest (task_context.task · state · recent_messages)
  ↓
POST /chat  ← X-Internal-Secret 검사 (없거나 다르면 401)
  ↓
SingleAgent
  ↓
LLM 호출 (8초 · 재시도 1회) ──실패──► app/ai/fallback.py 템플릿 · fallback=true
  ↓
현재 Task Context 확인 및 Tool 선택 (TODO)
  ↓
Spring API 또는 Financial RAG (TODO)
  ↓
ToolResult 조합 및 ChatResponse 생성 (TODO)
```

전체 채팅 기록을 모델의 장기 기억으로 사용하지 않는다. 실제 Task 상태는 Spring/DB가 관리하고, AI 서버는 요청에 포함된 현재 Task, 구조화된 현재 상태, 필요한 최소 최근 대화만 사용한다. `task_context.task`는 `REFLECTION` / `ANALYSIS` / `ACTION_PLAN` / `CLUSTER_NAMING` / `ANALYSIS_NARRATE` 5종이고 `state`의 구조는 05 §3이 정본이다.

## Directory 구조

```text
.
├── AGENTS.md                 # 에이전트가 먼저 읽는 전제 (CLAUDE.md는 포인터)
├── CONTRIBUTING.md           # 브랜치 · 커밋 · PR · 검사
├── README.md
├── docs/
│   ├── ONBOARDING.md
│   └── DEVELOPMENT.md
├── app/
│   ├── main.py               # FastAPI 앱 · GET /health
│   ├── api/chat.py           # POST /chat · X-Internal-Secret 검사
│   ├── agent/                # SingleAgent · prompt · state · tool_registry
│   ├── ai/fallback.py        # LLM 장애 템플릿 (FR-04-15)
│   ├── tools/                # Spring · RAG를 감싸는 얇은 Tool 6종
│   ├── reflection/           # 회고 후보 DTO · 표준 태그 enum · extract/normalize/validate
│   ├── rag/                  # 금융 RAG 경계 (P2)
│   ├── clients/spring_client.py  # Spring 내부 AI API 6종 — 유일한 HTTP 지점
│   ├── schemas/              # chat · tool · common(TaskType · ReflectionStep)
│   └── core/                 # config(Settings) · llm(타임아웃 · 재시도)
├── scripts/ingest_financial_docs.py
├── tests/                    # 외부 서비스 무호출
├── .github/                  # CI(pytest · docker build) · Issue · PR 템플릿
├── Dockerfile
├── requirements.txt          # 범위
├── requirements.lock         # 고정 (Python 3.12 컨테이너에서 생성)
└── .env.example
```

각 세부 모듈의 책임은 해당 폴더의 README에 설명한다. 처음 참여한다면 [온보딩 문서](docs/ONBOARDING.md)를 먼저 읽는다.

## 기술 스택

- Python 3.12 (팀 통일 — E-26)
- FastAPI, Uvicorn
- Pydantic, pydantic-settings
- httpx
- OpenAI Python SDK — `gpt-4o-mini` (E-25)
- PostgreSQL/pgvector (금융 RAG 저장소, P2)
- pytest

LangGraph, CrewAI 같은 Agent Framework나 복잡한 RAG Framework는 초기 범위에 포함하지 않는다. uv·pyproject를 쓰지 않고 `pip` + `venv`로 통일한다.

## 환경 변수

`.env.example`을 `.env`로 복사한 뒤 로컬 값을 설정한다. 실제 `.env`는 Git에 포함하지 않는다.

| 변수 | 필수 | 설명 | 기본값 |
|---|---:|---|---|
| `OPENAI_API_KEY` | 아니요 | OpenAI API 인증 키. 없으면 모든 `/chat`이 템플릿 응답(`fallback: true`) | 없음 |
| `OPENAI_MODEL` | 아니요 | 공통 LLM 모델 | `gpt-4o-mini` |
| `LLM_TIMEOUT_SECONDS` | 아니요 | LLM 1회 호출 타임아웃(초). 초과 시 1회 재시도 후 템플릿 (NFR-04) | `8` |
| `SPRING_BASE_URL` | Spring 연동 시 | Spring 서비스 Base URL | `http://localhost:8080` |
| `SPRING_TIMEOUT_SECONDS` | 아니요 | AI → Spring 내부 API Timeout(초) | `10` |
| `INTERNAL_SHARED_SECRET` | **예** | `X-Internal-Secret` 공유 시크릿. `sottaejap-server`의 `AI_SHARED_SECRET`과 같은 값. **비어 있으면 `/chat`이 전부 401** | 없음 |
| `DATABASE_URL` | RAG 연결 후 | PostgreSQL/pgvector 연결 문자열 | 없음 |
| `AI_SERVER_HOST` | 아니요 | Uvicorn 바인딩 Host | `0.0.0.0` |
| `AI_SERVER_PORT` | 아니요 | Uvicorn 포트 | `8000` |
| `PYTHONUTF8` | 아니요 | Windows 인코딩 강제 (07 §5-3) | `1` |

## 로컬 실행

```bash
python3.12 -m venv .venv          # Windows: py -3.12 -m venv .venv
source .venv/bin/activate         # Windows: .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.lock
cp .env.example .env              # Windows: Copy-Item .env.example .env
# .env의 INTERNAL_SHARED_SECRET을 팀 공유값으로 채운다
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

실행 후 다음 주소를 확인한다.

- Health: `http://localhost:8000/health`
- Swagger UI: `http://localhost:8000/docs`

기본 Chat 요청 (헤더가 없으면 401):

```bash
curl -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -H 'X-Internal-Secret: <INTERNAL_SHARED_SECRET>' \
  -d '{"message":"이번 소비를 돌아보고 싶어요","user_id":"1","task_context":{"task":"REFLECTION","status":"ACTIVE","state":{"step":"SATISFACTION"}}}'
```

`OPENAI_API_KEY`가 비어 있으면 `{"reply":"이 소비, 만족하셨나요?", ..., "fallback": true}`처럼 템플릿으로 응답한다. Spring `/internal-test/ai-ping`은 키 없이도 200이다.

Docker로 실행하려면:

```bash
docker build -t sottaejap-ai .
docker run --rm -p 8000:8000 --env-file .env sottaejap-ai
```

## 테스트 실행

```bash
pytest
```

테스트는 실제 OpenAI API, Spring API, PostgreSQL을 호출하지 않는다. `tests/conftest.py`가 시크릿을 고정하고 키를 비운다.

## 현재 구현 범위

완료:

- FastAPI 앱, `GET /health`, `POST /chat` + `X-Internal-Secret` 검사
- `ChatRequest → SingleAgent → LLM 1회 호출 또는 템플릿 폴백 → ChatResponse(fallback)` 흐름
- LLM 타임아웃 8초 · 재시도 1회 (`app/core/llm.py`)
- 폴백 템플릿 — 작업 5종 · 회고 단계 6종 · `reason_code` 5종 (`app/ai/fallback.py`)
- `SpringClient` 6종 경로 · 헤더 · 봉투 해제 (05 §3)
- 회고 DTO — 표준 태그 enum(목적 7 · 동행인 6) · 만족도 3택, 자유 문자열 거부
- 요청 단위 Agent 상태와 Tool Registry 골격, 여섯 개 Tool 경계
- 단순 Chunker, Embedding/Retriever 경계
- Dockerfile · `requirements.lock` · CI(pytest · docker build)

TODO:

- LLM 기반 의도 파악과 OpenAI Tool Calling 실행 루프
- 회고 Structured Output 추출과 사용자 확인 대화 (`normalize_purpose`·`normalize_companion` 경유)
- 금융 문서 Parser, Embedding, pgvector 적재 및 Top-K 검색 (P2 · FR-12)
- Tool 실패/Timeout을 `tool_results[].success = false`로 변환하는 정책

## 개발 원칙

- Tool과 Agent에 서비스 계산 또는 최종 판정 로직을 넣지 않는다.
- Tool 파일에서 `httpx`를 직접 사용하지 않는다.
- AI Agent가 DB를 직접 수정하지 않는다.
- 05 §3에 없는 Spring Endpoint를 임의로 만들지 않는다. 경로를 바꾸면 문서를 먼저 고친다.
- 자연어에서 확인할 수 없는 회고 값은 `None` 또는 `UNKNOWN`으로 유지한다. 표준 태그 밖의 값은 `None`이다.
- LLM 실패는 5xx가 아니라 템플릿 + `fallback: true` + 200이다.
- 기능별 프레임워크보다 단순하고 교체 가능한 모듈 경계를 우선한다.
- 모든 핵심 코드에 type hint와 짧은 module docstring을 사용한다.
- 새 기능은 관련 테스트와 문서를 함께 변경한다.

자세한 추가 절차와 테스트 기준은 [개발 문서](docs/DEVELOPMENT.md)를 따른다.
