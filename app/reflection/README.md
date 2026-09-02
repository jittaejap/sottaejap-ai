# Reflection 모듈

## 목적

사용자의 자연어 소비 회고를 검증 가능한 정형 후보 데이터로 바꾼다. AI가 만든 결과는 확정 사실이 아니라 사용자에게 보여주고 확인·수정할 수 있는 후보라는 전제를 유지한다.

예시:

```json
{
  "purpose": "야식",
  "companion": "친구",
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
Normalize: 자유입력을 표준 표현으로 변환
  ↓
Validate: 미확정 필드와 추가 질문 필요 여부 확인
  ↓
사용자 검증
  ↓
ReflectionTool을 통해 Spring에 저장
```

## UNKNOWN 처리

- 자연어로 확인할 수 없는 값은 임의로 추론하지 않는다.
- 텍스트 필드와 반복 의도는 `None`, 열거형 필드는 `UNKNOWN`을 허용한다.
- `needs_clarification`과 `uncertain_fields`로 추가 질문이 필요한 이유를 드러낸다.
- 만족도 보정이나 Reflection Score는 이 모듈이 계산하지 않는다.

현재 Extractor는 모두 미확정인 안전한 결과를 반환한다. 실제 LLM Structured Output 연결은 TODO이며, 연결 후에도 Pydantic 검증과 사용자 확인 단계를 유지해야 한다.

