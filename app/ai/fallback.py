"""LLM 장애 시 돌려줄 템플릿 응답 (FR-04-15 · NFR-04 · 06 R3).

LLM이 8초를 넘기거나 오류를 내면 Agent가 이 템플릿으로 `reply`를 채우고 `fallback=True`로
응답한다. 여기서는 Spring이 `task_context.state`에 실어 보낸 값만 문장에 넣는다.
집계에 없는 수치나 이유를 만들지 않는다 (NFR-02).
"""

from typing import Any

from app.schemas.common import ReflectionStep, TaskType

CLUSTER_NAME_MAX_LENGTH = 12

_REASON_SENTENCES: dict[str, str] = {
    "TIMESLOT_OUTLIER": "평소와 다른 시간대의 소비였어요.",
    "THRESHOLD_EXCEEDED": "설정하신 기준 금액을 넘은 소비였어요.",
    "REPEATED_LOW_SATISFACTION": "비슷한 소비에서 만족도가 낮았던 적이 있어요.",
    "ONBOARDING_SAMPLE": "최근 소비 중에서 함께 돌아볼 거래로 골랐어요.",
    "MANUAL_PICK": "직접 추가하신 거래예요.",
}

_REFLECTION_QUESTIONS: dict[ReflectionStep, str] = {
    ReflectionStep.SATISFACTION: "이 소비, 만족하셨나요?",
    ReflectionStep.PURPOSE: "어떤 목적의 소비였나요? 아래에서 골라 주세요.",
    ReflectionStep.COMPANION: "누구와 함께한 소비였나요?",
    ReflectionStep.REPEAT: "다음에도 비슷한 소비를 하실 것 같나요?",
    ReflectionStep.CONFIRM: "입력하신 내용을 확인해 주세요. 맞으면 저장할게요.",
}

_TASK_REPLIES: dict[TaskType, str] = {
    TaskType.ANALYSIS: "지금은 AI 설명을 준비할 수 없어요. 소비 분석 화면의 집계 결과를 확인해 주세요.",
    TaskType.ACTION_PLAN: "지금은 제안 이유를 설명드릴 수 없어요. 제안 목록에서 예상 절감액을 확인해 주세요.",
    TaskType.ANALYSIS_NARRATE: "이번 달 소비 특징은 잠시 후 다시 확인해 주세요.",
}

DEFAULT_REPLY = "지금은 답변을 만들 수 없어요. 잠시 후 다시 시도해 주세요."


def fallback_reply(task: TaskType | None, state: dict[str, Any]) -> str:
    """작업 종류와 현재 상태에 맞는 템플릿 문장을 돌려준다."""

    if task is TaskType.REFLECTION:
        return _reflection_reply(state)
    if task is TaskType.CLUSTER_NAMING:
        return _cluster_name(state)
    if task is None:
        return DEFAULT_REPLY
    return _TASK_REPLIES.get(task, DEFAULT_REPLY)


def _reflection_reply(state: dict[str, Any]) -> str:
    step = _optional_step(state.get("step"))
    if step is ReflectionStep.INTRO or step is None:
        return _intro(state)
    return _REFLECTION_QUESTIONS[step]


def _intro(state: dict[str, Any]) -> str:
    transaction = state.get("transaction")
    reason = _REASON_SENTENCES.get(str(state.get("reason_code")), "")
    lead = ""
    closing = "최근 소비 하나를 함께 돌아볼까요?"
    if isinstance(transaction, dict):
        merchant = transaction.get("merchant")
        amount = transaction.get("amount")
        if merchant and isinstance(amount, int | float):
            lead = f"{merchant}에서 {int(amount):,}원을 쓰셨네요."
            closing = "이 소비를 함께 돌아볼까요?"
    return " ".join(part for part in (lead, reason, closing) if part)


def _cluster_name(state: dict[str, Any]) -> str:
    """묶음 이름 1개, 12자 이내 (FR-05-05). LLM 없이 대표 가맹점명으로 대체한다."""

    merchants = state.get("sample_merchants")
    if isinstance(merchants, list) and merchants and isinstance(merchants[0], str):
        return merchants[0].strip()[:CLUSTER_NAME_MAX_LENGTH] or "반복 소비 묶음"
    return "반복 소비 묶음"


def _optional_step(value: Any) -> ReflectionStep | None:
    try:
        return ReflectionStep(value)
    except (TypeError, ValueError):
        return None
