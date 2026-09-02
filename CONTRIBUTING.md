# sottaejap-ai 협업 가이드

이 문서를 읽으면 브랜치를 만들고, 커밋하고, PR을 올리고, 병합 전 검사를 통과시킬 수
있습니다. 값의 정본은 `myDocs/07_기술스택_레포구성.md` §5·§6·§9입니다. 충돌하면 그쪽이
우선합니다.

## 1. Issue

작업은 Issue를 만든 뒤 시작합니다. `New issue`에서 양식(기능 개발 · 버그 수정 · 리팩터링 · 일반 작업)을
고르면 제목 접두사 `[Feat]` `[Fix]` `[Refactor]` `[Docs]` `[Chore]` `[Test]`가 붙습니다. 한 Issue에는
하나의 목적만 둡니다. 본선 30시간 동안은 Issue 없이 작업해도 됩니다.

## 2. 브랜치

기본 브랜치는 `main`이고 `develop`은 두지 않습니다.

| 브랜치      | 용도                                     |
| ----------- | ---------------------------------------- |
| `main`      | 배포 가능 상태만. 통합 브랜치를 겸합니다 |
| `feature/*` | 기능. 예: `feature/tool-calling`         |
| `fix/*`     | 수정. 예: `fix/fallback-intro`           |

이름은 영문 소문자와 하이픈만 씁니다. 본선 30시간 동안은 리뷰 대기로 막히지 않도록
`main` 직접 push를 허용합니다. 그 밖의 기간에는 PR을 거칩니다.

## 3. 커밋

`타입(범위): 한국어 설명` 형식입니다. 범위는 폴더 이름입니다.

```text
feat(agent): OpenAI Tool Calling 실행 루프
fix(fallback): CLUSTER_NAMING 템플릿 12자 초과 수정
chore(deps): requirements.lock 재생성
docs(agents): 폴백 200 규칙 추가
```

| 타입       | 용도                      |
| ---------- | ------------------------- |
| `feat`     | 기능 추가                 |
| `fix`      | 버그 수정                 |
| `refactor` | 동작을 유지하는 구조 개선 |
| `chore`    | 설정, 의존성, 빌드        |
| `test`     | 테스트 추가 또는 수정     |
| `docs`     | 문서만 변경               |

커밋 메시지에 `Co-Authored-By` 트레일러를 넣지 않습니다. 에이전트가 생성한 커밋도 같습니다.

## 4. PR

- 제목은 커밋과 같은 형식입니다.
- 본문에 **무엇을 바꿨는가 · 왜 · 어떻게 검증했는가**를 적습니다. 프롬프트나 템플릿 문구를 바꿨으면 전후 예시를 붙입니다.
- 통합 담당(고현석)이 리뷰한 뒤 병합합니다. AI 레포 담당은 오진호입니다.
- 관련 없는 변경을 한 PR에 섞지 않습니다.

## 5. 병합 전 검사

CI(`.github/workflows/ci.yml`)가 Python 3.12에서 아래를 돌립니다. 올리기 전에 로컬에서 먼저 통과시킵니다.

```bash
source .venv/bin/activate
pytest
```

테스트는 OpenAI · Spring · DB를 호출하지 않습니다. 아래를 바꿨다면 해당 항목을 수동으로 확인해 PR에 적습니다.

- `/chat` DTO · 시크릿 · 폴백을 바꿨다면: 서버를 띄우고 `curl`로 헤더 없이 401, 헤더 있이 200과 `fallback` 값
- `SpringClient` 경로를 바꿨다면: Spring 로컬 기동 후 `curl localhost:8080/internal-test/ai-ping` 200
- `Dockerfile` · `requirements.lock`을 바꿨다면: `docker build -t sottaejap-ai .` 성공

## 6. 계약 변경 절차

`/chat` DTO, `task_context.state` 구조, 표준 태그, Spring 내부 AI API 경로를 바꾸면 세 레포가 같이 깨집니다 (07 §6).

1. `myDocs/05_API_명세서.md` §3을 **먼저** 고칩니다. 문서가 계약입니다. 표준 태그는 `01_결정로그.md` §2입니다.
2. 팀 채널에 `[계약변경] /chat에 fallback 필드 추가` 형태로 한 줄 공지합니다.
3. 이 저장소에서는 `app/schemas/chat.py` · `app/schemas/common.py` · `app/reflection/schemas.py` ·
   `app/clients/spring_client.py`를 문서에 맞춰 고칩니다. 통합 담당(고현석)이 `sottaejap-server`의
   `AiClient` · `/internal/ai/*` 반영을 확인합니다.

코드가 문서를 앞서지 않습니다.

## 7. 버전과 도구

`requirements.txt`의 범위는 07 §1 표를 그대로 옮긴 값입니다. 임의로 올리지 않습니다.
설치는 `requirements.lock`(고정)으로 하고, 새 라이브러리를 추가할 때만 `requirements.txt`에 범위를 적은 뒤
lock을 다시 뽑습니다. lock은 로컬 파이썬 버전과 무관하게 **Python 3.12 기준**으로 해석합니다.
pip의 교차 해석 옵션을 쓰면 3.12가 설치되어 있지 않아도 됩니다.

```bash
pip install --python-version 3.12 --only-binary=:all: --platform manylinux2014_x86_64 --platform manylinux2014_aarch64 --platform macosx_11_0_arm64 --platform any --target /tmp/py312 -r requirements.txt
{ head -2 requirements.lock; pip freeze --path /tmp/py312 | sort -f; } > requirements.lock.new && mv requirements.lock.new requirements.lock
```

Docker가 떠 있다면 3.12 컨테이너에서 같은 결과를 얻습니다.

```bash
docker run --rm -v "$PWD":/w -w /w python:3.12-slim sh -c "pip install -q -r requirements.txt && pip freeze"
```

`requirements.txt`와 `requirements.lock`은 같은 커밋에 넣습니다. lock 첫 두 줄의 주석은 유지합니다.

## 8. macOS · Windows 혼용

07 §5가 정본입니다. 여기서는 이 저장소에서 실제로 걸리는 것만 적습니다.

- 최초 1회: macOS는 `git config --global core.autocrlf input`, Windows는 `false`.
- venv는 macOS `python3.12 -m venv .venv`, Windows `py -3.12 -m venv .venv`. 활성화는 `source .venv/bin/activate` /
  `.\.venv\Scripts\Activate.ps1`.
- `.env`는 터미널로 만듭니다. `cp .env.example .env` / `Copy-Item .env.example .env`.
  Windows 탐색기는 `.env.txt`를 만듭니다.
- 모든 `open()`에 `encoding="utf-8"`을 씁니다. `.env`의 `PYTHONUTF8=1`은 지우지 않습니다.
- 파일·폴더명은 영문 소문자와 하이픈만 씁니다.
- 줄바꿈은 `.gitattributes`가 LF로 강제합니다. diff가 파일 전체로 뜨면 CRLF가 섞인 것입니다.

## 9. 비밀값

`OPENAI_API_KEY` · `INTERNAL_SHARED_SECRET` · `DATABASE_URL`을 코드 · 로그 · 프롬프트 · PR에 남기지 않습니다.
`.env`는 커밋하지 않고 `.env.example`만 커밋합니다. `INTERNAL_SHARED_SECRET`은 `sottaejap-server`의
`AI_SHARED_SECRET`과 같은 값이고 팀 채널에서 한 번 공유해 고정합니다 (07 §3). CI의 값은 러너 안에서만 유효한 더미입니다.
