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
ReflectionTool을 통해 Spring에 저장
```

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

LLM 출력을 그대로 믿지 않는다. 표준 태그 목록 밖 문자열은 `normalize_*`가 `None`으로 만들고, Pydantic 검증과 사용자 확인 단계는 그대로 유지한다. `LLMUnavailableError`는 여기서 잡지 않는다 — 폴백 전환은 `SingleAgent.run` 한 곳이 담당한다.

추출기를 부르는 곳은 `app/agent/handlers/reflection.py`(REFLECTION Handler)다. 그 Handler가 확정값과 병합하고 다음 질문을 붙여 `/chat` 응답을 만든다. `to_extraction()`은 LLM 출력과 Spring 확정값을 **같은 규칙으로** 좁히려고 공개해 둔 함수다 — 좁히는 규칙이 두 벌이면 한쪽만 고쳐져 표준 태그 밖 값이 샌다.

