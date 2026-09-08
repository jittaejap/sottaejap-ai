"""Single Agent가 사용할 시스템 프롬프트를 관리한다."""

import json

from app.agent.state import AgentState

SYSTEM_PROMPT = """당신은 소때잡의 소비 회고 도우미입니다.
자연어 의도를 파악하고 필요한 Tool 결과를 조합해 이해하기 쉽게 설명합니다.
데이터, 규칙, 계산, 최종 판정은 Spring의 결과를 따릅니다.
확인할 수 없는 사용자 정보는 추측하지 말고 추가 확인이 필요하다고 알립니다.
"""


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
    if state.last_question:
        context_lines.append(f"직전에 사용자에게 한 질문: {state.last_question}")
    if instruction:
        context_lines.append(instruction)

    if not context_lines:
        return SYSTEM_PROMPT
    context = "\n".join(context_lines)
    return f"{SYSTEM_PROMPT}\n{context}\n"
