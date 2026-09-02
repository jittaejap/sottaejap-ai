# 소때잡 AI Server

소때잡의 자연어 소비 회고, Tool Calling, 금융 지식 검색을 담당하는 Python/FastAPI 서버다. 이 저장소의 목표는 완성된 AI 기능이 아니라 여러 개발자가 같은 책임과 경계를 이해하고 기능을 안전하게 추가할 수 있는 실행 가능한 초기 Repository를 제공하는 것이다.

## AI 서버 역할

AI 서버는 다음 작업을 조정한다.

- Single Agent 실행과 사용자 자연어 의도 파악
- 현재 Task Context를 이용한 Tool 선택
- 사용자 회고의 후보 값 구조화와 사용자 확인 요청
- Tool 결과 조합 및 자연어 설명
- 금융 질문을 위한 내부 RAG 호출
- Spring 서비스와의 HTTP 통신

데이터 영속화, 서비스 규칙, 수치 계산, 최종 판정은 AI 서버의 책임이 아니다.

## Spring과 AI 역할 분리

| Spring | Python AI Server |
|---|---|
| 거래·회고·목표 데이터 관리 | Single Agent와 자연어 이해 |
| 개인 Baseline 및 Anomaly Score 계산 | 자연어 회고 구조화 |
| 후보 선정, 반복 행동 최종 분류 | Tool 선택과 결과 조합 |
| 만족도 보정, 절감액·감소액·달성률 계산 | 금융 RAG와 자연어 설명 |
| Rule Engine과 최종 데이터·판정 | Spring API 통신 |

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
Vue
  ↓
Spring
  ↓
FastAPI / Single Agent
  ↓
Tool
  ├─ 거래·회고·분석·행동 제안·메모리 → Spring API
  └─ 금융 지식 → Python Financial RAG → pgVector (TODO)
```

## 요청 흐름

```text
ChatRequest
  ↓
POST /chat
  ↓
SingleAgent
  ↓
현재 Task Context 확인 및 Tool 선택 (TODO)
  ↓
Spring API 또는 Financial RAG (TODO)
  ↓
ToolResult 조합 및 ChatResponse 생성 (TODO)
```

전체 채팅 기록을 모델의 장기 기억으로 사용하지 않는다. 실제 Task 상태는 Spring/DB가 관리하고, AI 서버는 요청에 포함된 현재 Task, 구조화된 현재 상태, 필요한 최소 최근 대화만 사용한다.

## Directory 구조

```text
.
├── README.md
├── docs/
│   ├── ONBOARDING.md
│   └── DEVELOPMENT.md
├── app/
│   ├── main.py
│   ├── api/chat.py
│   ├── agent/
│   │   ├── agent.py
│   │   ├── prompt.py
│   │   ├── state.py
│   │   ├── tool_registry.py
│   │   └── README.md
│   ├── tools/
│   │   ├── transaction_tool.py
│   │   ├── reflection_tool.py
│   │   ├── analysis_tool.py
│   │   ├── action_plan_tool.py
│   │   ├── memory_tool.py
│   │   ├── financial_rag_tool.py
│   │   └── README.md
│   ├── reflection/
│   │   ├── extractor.py
│   │   ├── normalizer.py
│   │   ├── validator.py
│   │   ├── schemas.py
│   │   └── README.md
│   ├── rag/
│   │   ├── chunker.py
│   │   ├── embedding.py
│   │   ├── retriever.py
│   │   ├── prompt.py
│   │   ├── schemas.py
│   │   └── README.md
│   ├── clients/spring_client.py
│   ├── schemas/
│   │   ├── chat.py
│   │   ├── tool.py
│   │   └── common.py
│   └── core/
│       ├── config.py
│       └── llm.py
├── scripts/ingest_financial_docs.py
├── tests/
├── .env.example
├── .gitignore
└── requirements.txt
```

각 세부 모듈의 책임은 해당 폴더의 README에 설명한다. 처음 참여한다면 [온보딩 문서](docs/ONBOARDING.md)를 먼저 읽는다.

## 기술 스택

- Python 3.12+
- FastAPI, Uvicorn
- Pydantic, pydantic-settings
- httpx
- OpenAI Python SDK(후속 Tool Calling 연동용)
- PostgreSQL/pgVector(금융 RAG 저장소로 예정)
- pytest

LangGraph, CrewAI 같은 Agent Framework나 복잡한 RAG Framework는 초기 범위에 포함하지 않는다.

## 환경 변수

`.env.example`을 `.env`로 복사한 뒤 로컬 값을 설정한다. 실제 `.env`는 Git에 포함하지 않는다.

| 변수 | 필수 | 설명 | 기본값 |
|---|---:|---|---|
| `OPENAI_API_KEY` | Tool Calling 연결 후 | OpenAI API 인증 키 | 없음 |
| `OPENAI_MODEL` | 아니요 | 공통 LLM 모델 | `gpt-4o-mini` |
| `SPRING_BASE_URL` | Spring 연동 시 | Spring 서비스 Base URL | `http://localhost:8080` |
| `DATABASE_URL` | RAG 연결 후 | PostgreSQL/pgVector 연결 문자열 | 없음 |
| `AI_SERVER_HOST` | 아니요 | Uvicorn 바인딩 Host | `0.0.0.0` |
| `AI_SERVER_PORT` | 아니요 | Uvicorn 포트 | `8000` |
| `SPRING_TIMEOUT_SECONDS` | 아니요 | Spring HTTP Timeout(초) | `10` |

## 로컬 실행

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

실행 후 다음 주소를 확인한다.

- Health: `http://localhost:8000/health`
- Swagger UI: `http://localhost:8000/docs`

기본 Chat 요청:

```bash
curl -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"이번 소비를 돌아보고 싶어요","user_id":"user-1"}'
```

## 테스트 실행

```bash
pytest
```

테스트는 실제 OpenAI API, Spring API, PostgreSQL을 호출하지 않는다.

## 현재 구현 범위

완료:

- FastAPI 앱, `GET /health`, `POST /chat`
- `ChatRequest → SingleAgent → ChatResponse` 실행 흐름
- 요청 단위 Agent 상태와 Tool Registry 골격
- SpringClient와 여섯 개 Tool 경계
- 회고 DTO, Extract/Normalize/Validate 경계
- 단순 Chunker, Embedding/Retriever 경계
- 환경 설정, OpenAI Client 골격, 테스트

TODO:

- LLM 기반 의도 파악과 OpenAI Tool Calling 실행 루프
- 확정된 Spring Endpoint·요청·응답 DTO 연결
- 회고 Structured Output 추출과 사용자 확인 대화
- 금융 문서 Parser, Embedding, pgVector 적재 및 Top-K 검색
- Tool 실패/Timeout을 사용자 응답으로 안전하게 변환하는 정책

## 개발 원칙

- Tool과 Agent에 서비스 계산 또는 최종 판정 로직을 넣지 않는다.
- Tool 파일에서 `httpx`를 직접 사용하지 않는다.
- AI Agent가 DB를 직접 수정하지 않는다.
- 미확정 Spring Endpoint를 임의로 만들지 않는다.
- 자연어에서 확인할 수 없는 회고 값은 `None` 또는 `UNKNOWN`으로 유지한다.
- 기능별 프레임워크보다 단순하고 교체 가능한 모듈 경계를 우선한다.
- 모든 핵심 코드에 type hint와 짧은 module docstring을 사용한다.
- 새 기능은 관련 테스트와 문서를 함께 변경한다.

자세한 추가 절차와 테스트 기준은 [개발 문서](docs/DEVELOPMENT.md)를 따른다.

