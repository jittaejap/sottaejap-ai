"""Single Agent가 사용할 시스템 프롬프트를 관리한다."""

import json

from app.agent.state import AgentState

SYSTEM_PROMPT = """당신은 소때잡의 소비 회고 도우미입니다.
자연어 의도를 파악하고 필요한 Tool 결과를 조합해 이해하기 쉽게 설명합니다.
데이터, 규칙, 계산, 최종 판정은 Spring의 결과를 따릅니다.
확인할 수 없는 사용자 정보는 추측하지 말고 추가 확인이 필요하다고 알립니다.
응답은 해요체로 작성하고 반말, 격식체, 이모지는 사용하지 않습니다.
한두 문장의 한 문단으로 짧게 답합니다.
사용자의 소비를 부정적으로 단정하지 않습니다.
사용자에게 '후회'를 유도하는 언어를 사용하지 않습니다.
'탈락', '아웃', 'Out'처럼 소비를 판결하는 어휘를 사용하지 않습니다.
지킬 만한 소비가 있으면 그것부터 먼저 언급합니다.
응답 예시:
- "이번 달 식비는 계획한 금액 안으로 확인돼요. 배달 소비는 지난달보다 늘어난 것으로 나와요."
- "확인된 근거가 없어 지금은 소비 흐름을 설명하기 어려워요."
"""


# build_system_prompt()가 SYSTEM_PROMPT 뒤에 Task 지시문을 붙이는 구조라, LLM은
# 나중에 붙은 지시문 쪽을 더 강하게 따른다 — SYSTEM_PROMPT의 해요체 규칙만 믿으면
# 밀린다(docs/DEVELOPMENT.md §12 · #46 · #40). 문장을 만드는 Task 지시문에는 이
# 규칙을 직접 넣는다. 한 곳(여기)에서만 문구를 바꾸도록 상수로 공유한다 —
# CLUSTER_NAMING처럼 12자 라벨만 뽑는 자리에는 쓰지 않는다.
HAEYO_RULE = '모든 문장은 "~요"로 끝나는 해요체로 씁니다. 반말로 끝내지 않습니다.'


def build_system_prompt(state: AgentState, instruction: str = "") -> str:
    """공통 프롬프트에 현재 맥락과 Task별 지시문을 순서대로 덧붙인다."""

    context_lines: list[str] = []
    if state.task is not None:
        context = json.dumps(state.structured_state, ensure_ascii=False)
        context_lines.extend(
            [
                f"현재 작업: {state.task.value}",
                f"현재 상태(JSON): {context}",
            ]
        )
    if instruction:
        context_lines.append(instruction)

    if not context_lines:
        return SYSTEM_PROMPT
    context = "\n".join(context_lines)
    return f"{SYSTEM_PROMPT}\n{context}\n"
