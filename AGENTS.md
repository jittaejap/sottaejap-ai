# AGENTS.md

이 저장소에서 코딩 에이전트(Claude Code · Codex)가 먼저 읽는 파일입니다. **규칙의 본문은
여기에 두지 않고 정본 문서를 가리킵니다.** 같은 규칙이 두 곳에 있으면 반드시 어긋나기
때문입니다. 여기에는 **모르면 반드시 틀리는 전제**만 적습니다.

## 정본 문서

| 알고 싶은 것                                   | 문서                                             |
| ---------------------------------------------- | ------------------------------------------------ |
| 모든 결정의 출처                               | `myDocs/01_결정로그.md` (충돌 시 이 문서가 우선) |
| 회고 표준 태그 · FR/NFR 번호                   | `myDocs/02_요구사항_정의서.md`                   |
| `/chat` DTO · `task_context.state` 구조 · Spring 내부 AI API 6종 · 타임아웃 | `myDocs/05_API_명세서.md` §3 |
| 스택 버전 · 폴더 구조 · 환경 변수 · OS 규칙    | `myDocs/07_기술스택_레포구성.md`                 |
| 모듈별 책임과 기능 추가 절차                   | [docs/DEVELOPMENT.md](./docs/DEVELOPMENT.md) · 각 폴더의 `README.md` |
| 브랜치 · 커밋 · PR · 검사 명령                 | [CONTRIBUTING.md](./CONTRIBUTING.md)             |
| 설치와 실행                                    | [README.md](./README.md)                         |

`myDocs/`는 팀 공유 폴더에 있고 이 저장소 밖입니다. 없으면 팀원에게 요청합니다.

## 고정된 것 — 임의로 바꾸지 않는다 (E-25 · E-26)

Python **3.12** · `pip` + `venv` · `requirements.txt`(범위) + `requirements.lock`(고정) · OpenAI `gpt-4o-mini`

- uv · poetry · `pyproject.toml`을 도입하지 않습니다. LangGraph · CrewAI 같은 Agent 프레임워크도 넣지 않습니다.
- 의존성을 바꾸면 `requirements.txt`와 `requirements.lock`을 같은 커밋에 넣습니다. lock은 **3.12 기준으로 해석**해서
  뽑습니다 (`pip install --python-version 3.12 ...` — CONTRIBUTING §7). 로컬 파이썬이 3.13·3.14여도 그 venv의 `pip freeze`를 lock으로 쓰지 않습니다.
- 임베딩 모델 · pgvector 클라이언트 · numpy는 지금 없습니다. 금융 RAG(P2, FR-12) 착수 때 05·07을 먼저 고친 뒤 추가합니다.

## 이 서버는 계산하지 않는다 (E-18)

```
Spring = 데이터 / 규칙 / 계산 / 최종 판정
Python = Agent / 자연어 / Tool Calling / RAG / 설명
```

- Baseline · Anomaly Score · 묶음 · 롤업 · 만족도 보정 · 판정(`verdict`) · 절감액 · 달성률을 **여기서 만들지 않습니다.**
  Tool은 `SpringClient` 결과를 그대로 넘기고, Agent는 그것을 문장으로 바꾸기만 합니다.
- `reason_code`는 Spring이 `state`에 실어 보냅니다. AI가 `reason_code` 없이 이유를 지어내는 경로는 없습니다 (NFR-02).
  `ANALYSIS_NARRATE`는 `state.by_verdict` · `by_category`에 없는 수치를 문장에 넣지 않습니다.
- `task_context.status`는 Spring 소유입니다. AI는 읽기만 하고 바꾸지 않습니다.

## HTTP는 두 군데뿐이다 (E-19 · 05 §3)

- **들어오는 것:** `POST /chat` 하나. `X-Internal-Secret` 헤더가 `INTERNAL_SHARED_SECRET`과 다르면 401이고,
  **시크릿이 비어 있으면 모든 요청이 401**입니다 (Spring 쪽 규칙과 대칭). "로컬이니까" 비워 두면 ai-ping이 죽습니다.
  `/health`만 열려 있습니다.
- **나가는 것:** `app/clients/spring_client.py`의 6개 메서드가 `/internal/ai/users/{userId}/*`를 부릅니다.
  경로는 05 §3 표와 1:1이고 헤더는 같은 시크릿입니다. Tool 파일에서 `httpx`를 쓰지 않습니다.
- `SpringClient._request`는 봉투 `{ success, data | error }`를 벗겨 **`data`만** 돌려줍니다. `success: false`는
  `SpringApiError(code)`입니다. 응답 키는 **camelCase 그대로**이고 변환하지 않습니다.
- 경계 명명: `/chat` 요청·응답은 **snake_case**, Spring 내부 API 응답은 **camelCase**입니다 (E-24). 이 저장소 안에서는
  "reflection"(회고)을 쓰고 Spring·클라이언트의 "retrospect"와 같은 개념입니다.
- Spring이 `/chat`에서 422 `Field required: body`를 받으면 AI 코드가 아니라 Spring `AiClient`의 HTTP/2 업그레이드
  문제입니다 (server AGENTS.md). 여기서 고치려 들지 않습니다.

## 회고 값은 표준 태그 또는 null (E-20 · E-23)

- `Purpose` 7종 · `Companion` 6종은 `app/reflection/schemas.py`의 enum이고 **값이 한국어 문자열**입니다
  (`"충동"`, `"혼자"`). 목록은 01 §2 · 02 FR-04-04·05와 글자 단위로 같아야 합니다.
- `Satisfaction`은 `HIGH / LOW / UNKNOWN` 3택입니다. `MEDIUM`은 없습니다. 다시 넣지 않습니다.
- 자유 문자열은 `ReflectionExtraction` 생성 시 `ValidationError`입니다. LLM 출력은 반드시
  `normalize_purpose` · `normalize_companion`을 거쳐 표준 태그 또는 `None`으로 만든 뒤 DTO에 넣습니다.
  `None`은 사용자에게 되묻는 값(`uncertain_fields`)이지 오류가 아닙니다.

## LLM 폴백은 200이다 (FR-04-15 · NFR-04)

- `LLMClient.generate`가 `LLM_TIMEOUT_SECONDS`(8초) 안에 못 끝나거나 오류를 내면 **정확히 1회** 재시도한 뒤
  `LLMUnavailableError`를 올립니다. SDK 자체 재시도는 꺼져 있습니다 (`max_retries=0`). 재시도 정책을 다른 곳에 복제하지 않습니다.
- Agent는 그 오류와 `LLMNotConfiguredError`(키 없음)를 잡아 `app/ai/fallback.py` 템플릿으로 `reply`를 채우고
  **`fallback: true` · HTTP 200**으로 응답합니다. 5xx로 바꾸지 않습니다. 클라이언트는 이 값으로 템플릿 배너를 띄웁니다 (S11).
- 템플릿 문장은 `state`에 있는 값만 씁니다. `CLUSTER_NAMING` 폴백은 12자 이내여야 합니다 (FR-05-05).

## 테스트는 외부를 부르지 않는다

- `tests/conftest.py`가 `INTERNAL_SHARED_SECRET`을 고정하고 `OPENAI_API_KEY`를 비웁니다. 실제 OpenAI · Spring · DB를
  호출하는 테스트를 넣지 않습니다. Agent에는 `FakeLLM`을, `SpringClient`에는 `httpx.MockTransport`를 주입합니다.
- `/chat` 테스트는 `app.dependency_overrides[get_agent]`로 Agent를 교체합니다. 모듈 전역 `_agent`를 몽키패치하지 않습니다.

## 알려진 갭 — 지어내지 말고 보고한다

- Tool Calling 실행 루프 · 회고 Structured Output · 금융 RAG 적재는 TODO입니다. Agent는 지금 LLM 1회 호출 또는 폴백만 합니다.
- Spring → AI 타임아웃(15초)과 AI 내부 합계(LLM 8초 + Spring 10초 × 호출 수)의 정합은 9/7 실측 후 확정입니다 (07 §10 리스크 4).
  한 요청에서 Spring을 여러 번 부르는 코드를 넣으면 이 표를 먼저 고칩니다.

## OS 혼용 (07 §5)

- 파일·폴더명은 영문 소문자와 하이픈만. `open()`에는 항상 `encoding=`을 씁니다. `.env`에 `PYTHONUTF8=1`이 있습니다.
- `.env`는 터미널로 만듭니다. `.env.example`만 커밋합니다. 줄바꿈은 `.gitattributes`가 LF로 강제합니다.
- Windows는 `py -3.12 -m venv .venv` · `.\.venv\Scripts\Activate.ps1`입니다.
- 커밋 메시지에 `Co-Authored-By` 트레일러를 넣지 않습니다.
- `main`에 직접 push하지 않습니다(본선 30시간만 예외). 흐름은 `Issue → 작업 브랜치 → main 대상 PR → 리뷰 → Squash and merge`이고, 규칙은 [CONTRIBUTING.md](./CONTRIBUTING.md)가 정본입니다.

## 완료 보고

작업을 끝내면 **바꾼 것 · 지킨 계약 · 실행한 검사와 결과 · 실행하지 못한 검증과 이유 · 남은 위험**을 구분해 적습니다.
"성공"으로 뭉뚱그리지 않습니다. CI 통과와 로컬 통과를 구분하고, OpenAI 키 없이 돌린 것은 그렇게 적습니다.
