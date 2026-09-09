# Reflection 모듈

## 목적

사용자의 자연어 소비 회고를 검증 가능한 정형 후보 데이터로 바꾼다. AI가 만든 결과는 확정 사실이 아니라 사용자에게 보여주고 확인·수정할 수 있는 후보라는 전제를 유지한다.

예시:

```json
{
  "purpose": "충동",
  "companion": "혼자",
  "satisfaction": "LOW",
  "repeat_intention": null,
  "needs_clarification": true,
  "uncertain_fields": ["repeat_intention"]
}
```

## 처리 흐름

```text
Natural Language
  ↓
Extract: 문장에 드러난 후보 추출
  ↓
Normalize: 자유입력을 표준 태그(목적 7 · 동행인 6)로 변환, 불일치는 None
  ↓
Validate: 미확정 필드와 추가 질문 필요 여부 확인
  ↓
사용자 검증
  ↓
Spring이 저장 (`POST /retrospects`)
```

저장은 이 모듈도 REFLECTION Handler도 하지 않는다. Handler는 후보값을 `/chat` 응답에 실을 뿐이고, 사용자가 확인한 뒤 클라이언트가 부르는 `POST /retrospects`가 저장한다 (05 §3 · E-18).

## UNKNOWN 처리

- 자연어로 확인할 수 없는 값은 임의로 추론하지 않는다.
- `purpose`·`companion`은 표준 태그 enum(`Purpose` 7종 · `Companion` 6종, 값은 한국어 문자열) 또는 `None`이다. 자유 문자열은 DTO 생성 시 거부된다 (E-20).
- `satisfaction`은 `HIGH / LOW / UNKNOWN` 3택이다. `MEDIUM`은 없다 (E-23).
- 반복 의도는 `None`을 허용한다.
- `needs_clarification`과 `uncertain_fields`로 추가 질문이 필요한 이유를 드러낸다.
- 만족도 보정이나 Reflection Score는 이 모듈이 계산하지 않는다.

Extractor는 LLM을 **1회만** 부르고 그 한 응답에서 후보값과 공감 한마디(`ack`)를 함께 받는다. 값과 문장을 따로 부르면 NFR-04의 6초 예산이 두 배가 된다. 반환값은 `ReflectionTurn(extraction, ack)`이고, `ack`는 `reply`를 만들 때 쓰는 내부 값이라 `ReflectionExtraction`에 넣지 않는다 — 그 DTO는 05 API 명세서 §3의 `tool_results[].data` 계약이다.

직전 assistant 질문은 사용자의 짧은 답이 어느 항목에 대한 것인지 판단할 때만 참고하고, 질문 문장에만 등장한 값은 추출하지 않는다.

`ack`는 필수 키다. 값만 있고 문장이 비어 있으면 `LLMUnavailableError`를 올려 폴백 템플릿으로 보낸다 — 공감 없이 질문만 던지는 응답이 `fallback=False`로 나가는 것보다 낫다. 문체 품질은 프롬프트의 몫이고 코드는 문장이 실제로 있는지만 본다.

추출 프롬프트의 값 규칙은 **실측으로 필요가 확인된 것만** 들어 있다. `scripts/eval_reflection_extraction.py`를 실제 LLM으로 돌려 과잉추론이나 과소추출이 나온 자리에만 넣었고, 지웠을 때 다시 나빠지는 것을 확인했다. 방법론과 실측치는 `docs/DEVELOPMENT.md` §11에 있고, 규칙이 문자열에서 사라지지 않도록 `tests/test_reflection_prompt.py`가 못박는다 — 평가 스크립트는 `OPENAI_API_KEY`가 있어야 돌아서 CI가 지켜주지 못하기 때문이다.

태그 힌트는 **정의가 아니라 구분 규칙**이다. 정본(01 §2 · 02 FR-04-04·05)에 선택지 이름만 있고 각 태그의 정의가 없어서, 프롬프트가 "식사란 무엇이다"를 새로 정하면 근거 없는 해석을 AI가 만드는 셈이 된다 (NFR-02). 발화를 한 태그로 매핑하는 문장은 어느 헤더 아래에 두든 모델에게 정의로 전달되므로, **실측에서 실제로 충돌이 난 한 쌍(`식사` · `만남·사교`)만** 남기고 어느 것도 안 걸리면 `None`으로 돌아간다. 태그 정의를 넣을지는 정본 결정이 먼저다.

**과잉추론은 되묻기 자체를 없앤다.** server `RetrospectChatSupport.nextStep()`은 값이 차 있으면 그 단계를 묻지 않으므로, 지어낸 값은 사용자가 못 알아채면 묶음 키(02 FR-05-02)에 그대로 저장된다. `None`은 되묻기 한 번을 더 만들 뿐이다 (FR-04-08). 그래서 이 모듈은 재현율보다 정밀도를 우선한다.

LLM 출력을 그대로 믿지 않는다. 표준 태그 목록 밖 문자열은 `normalize_*`가 `None`으로 만들고, Pydantic 검증과 사용자 확인 단계는 그대로 유지한다. `LLMUnavailableError`는 여기서 잡지 않는다 — 폴백 전환은 `SingleAgent.run` 한 곳이 담당한다.

추출기를 부르는 곳은 `app/agent/handlers/reflection.py`(REFLECTION Handler)다. 그 Handler가 확정값과 병합하고 다음 질문을 붙여 `/chat` 응답을 만든다. `to_extraction()`은 LLM 출력과 Spring 확정값을 **같은 규칙으로** 좁히려고 공개해 둔 함수다 — 좁히는 규칙이 두 벌이면 한쪽만 고쳐져 표준 태그 밖 값이 샌다.

