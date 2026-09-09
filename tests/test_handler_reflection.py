"""REFLECTION Handler가 6단계 회고 대화 계약을 지키는지 확인한다 (05 §3 · FR-04)."""

import asyncio
from typing import Any

from app.agent.handlers import HANDLERS, reflection
from app.agent.handlers.base import HandlerContext
from app.agent.state import AgentState
from app.agent.tool_registry import ToolRegistry
from app.ai.fallback import REFLECTION_QUESTIONS, fallback_reply
from app.schemas.chat import ChatMessage
from app.schemas.common import ReflectionStep, TaskType
from app.schemas.tool import ToolName
from tests.conftest import FakeLLM

_TRANSACTION = {
    "id": 1043,
    "occurred_at": "2026-08-22T23:10:00+09:00",
    "merchant": "○○배달",
    "amount": 12000,
    "category": "배달",
    "time_slot": "NIGHT",
}
_NOTHING_CONFIRMED = {
    "satisfaction": "UNKNOWN",
    "purpose": None,
    "companion": None,
    "repeat_intention": None,
}


def _state(step: str, confirmed: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "transaction": _TRANSACTION,
        "reason_code": "TIMESLOT_OUTLIER",
        "reflection": confirmed if confirmed is not None else dict(_NOTHING_CONFIRMED),
        "step": step,
    }


def _context(
    llm: FakeLLM,
    state: dict[str, Any],
    message: str = "그냥 배고파서 혼자 시켰어요",
    last_question: str = "",
) -> HandlerContext:
    recent = [ChatMessage(role="assistant", content=last_question)] if last_question else []
    return HandlerContext(
        state=AgentState(message=message, structured_state=state, recent_messages=recent),
        llm=llm,  # type: ignore[arg-type]
        tools=ToolRegistry(),
    )


def _run(llm: FakeLLM, state: dict[str, Any], **kwargs: Any) -> Any:
    return asyncio.run(reflection.handle(_context(llm, state, **kwargs)))


def test_reflection_is_registered() -> None:
    assert HANDLERS[TaskType.REFLECTION] is reflection.handle


def test_intro_explains_selection_without_extracting() -> None:
    llm = FakeLLM(reply="○○배달에서 12,000원을 쓰셨네요. 함께 돌아볼까요?")

    response = _run(llm, _state("INTRO"), message="회고를 시작할게요")

    assert response.reply == "○○배달에서 12,000원을 쓰셨네요. 함께 돌아볼까요?"
    assert len(llm.calls) == 1
    # 선정 이유는 폴백과 같은 문장표에서 온다 — reason_code를 날것으로 넘기지 않는다.
    assert "평소와 다른 시간대의 소비였어요." in llm.prompts[0]
    assert "TIMESLOT_OUTLIER" not in llm.prompts[0]
    # 인사에는 후보값을 싣지 않는다 — Spring이 확정값을 그대로 유지한다.
    assert response.tool_results == []
    assert response.needs_clarification is False


def test_reply_is_ack_plus_next_question() -> None:
    llm = FakeLLM(json_reply={"satisfaction": "LOW", "ack": "배가 고프면 그럴 수 있어요."})

    response = _run(llm, _state("SATISFACTION"))

    assert response.reply == (
        f"배가 고프면 그럴 수 있어요. {REFLECTION_QUESTIONS[ReflectionStep.PURPOSE]}"
    )
    assert len(llm.calls) == 1


def test_multiple_values_in_one_sentence_skip_steps() -> None:
    llm = FakeLLM(
        json_reply={
            "satisfaction": "LOW",
            "purpose": "충동",
            "companion": "혼자",
            "ack": "그러셨군요.",
        }
    )

    response = _run(llm, _state("SATISFACTION"))

    # 만족도·목적·동행인이 한 번에 확정돼 반복의향으로 건너뛴다.
    assert REFLECTION_QUESTIONS[ReflectionStep.REPEAT] in response.reply
    assert response.tool_results[0].data["uncertain_fields"] == ["repeat_intention"]


def test_all_values_confirmed_moves_to_confirm() -> None:
    llm = FakeLLM(json_reply={"repeat_intention": False, "ack": "알겠어요."})
    confirmed = {
        "satisfaction": "LOW",
        "purpose": "충동",
        "companion": "혼자",
        "repeat_intention": None,
    }

    response = _run(llm, _state("REPEAT", confirmed))

    assert REFLECTION_QUESTIONS[ReflectionStep.CONFIRM] in response.reply
    assert response.needs_clarification is False
    assert response.tool_results[0].data["uncertain_fields"] == []


def test_confirmed_values_win_over_extraction() -> None:
    llm = FakeLLM(
        json_reply={
            "satisfaction": "HIGH",
            "purpose": "식사",
            "companion": "친구",
            "repeat_intention": True,
            "ack": "그러셨군요.",
        }
    )
    confirmed = {
        "satisfaction": "LOW",
        "purpose": "충동",
        "companion": "혼자",
        "repeat_intention": False,
    }

    response = _run(llm, _state("CONFIRM", confirmed))

    assert response.tool_results[0].data == {
        "purpose": "충동",
        "companion": "혼자",
        "satisfaction": "LOW",
        "repeat_intention": False,
        "needs_clarification": False,
        "uncertain_fields": [],
    }


def test_tool_result_matches_api_contract() -> None:
    llm = FakeLLM(json_reply={"purpose": "충동", "companion": "혼자", "ack": "그러셨군요."})

    response = _run(llm, _state("PURPOSE"))

    result = response.tool_results[0]
    assert result.tool_name is ToolName.REFLECTION
    assert result.success is True
    # 05 §3 응답 예시와 같은 모양이다.
    assert result.data == {
        "purpose": "충동",
        "companion": "혼자",
        "satisfaction": "UNKNOWN",
        "repeat_intention": None,
        "needs_clarification": True,
        "uncertain_fields": ["satisfaction", "repeat_intention"],
    }
    assert response.needs_clarification is True


def test_values_outside_standard_tags_do_not_leak() -> None:
    llm = FakeLLM(json_reply={"purpose": "야식", "ack": "그러셨군요."})
    confirmed = {
        "satisfaction": "UNKNOWN",
        "purpose": "배달 음식",
        "companion": None,
        "repeat_intention": None,
    }

    response = _run(llm, _state("PURPOSE", confirmed))

    assert response.tool_results[0].data["purpose"] is None


def test_last_question_is_passed_to_the_extractor() -> None:
    llm = FakeLLM(json_reply={"satisfaction": "LOW", "ack": "아쉬우셨겠어요."})

    _run(llm, _state("SATISFACTION"), message="별로였어요", last_question="이 소비, 만족하셨나요?")

    assert "이 소비, 만족하셨나요?" in llm.prompts[0]


def test_question_matches_fallback_when_nothing_is_extracted() -> None:
    """폴백일 때와 같은 질문이 나가야 한다 — 사용자가 보는 순서가 흔들리지 않는다."""

    # 각 단계에서 "그 단계까지 확정된" 값. Spring이 step을 계산하는 순서와 같다.
    progress: list[tuple[ReflectionStep, dict[str, Any]]] = [
        (ReflectionStep.SATISFACTION, {}),
        (ReflectionStep.PURPOSE, {"satisfaction": "LOW"}),
        (ReflectionStep.COMPANION, {"satisfaction": "LOW", "purpose": "충동"}),
        (
            ReflectionStep.REPEAT,
            {"satisfaction": "LOW", "purpose": "충동", "companion": "혼자"},
        ),
    ]

    for step, confirmed_values in progress:
        confirmed = dict(_NOTHING_CONFIRMED) | confirmed_values
        state = _state(step.value, confirmed)

        response = _run(FakeLLM(json_reply={"ack": "그러셨군요."}), state)

        assert response.reply.endswith(fallback_reply(TaskType.REFLECTION, state))
