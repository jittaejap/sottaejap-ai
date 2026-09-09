"""ANALYSIS_NARRATE Handler의 숫자 가드레일이 근거 안 숫자만 통과시키는지 확인한다."""

import asyncio
from typing import Any

from app.agent.handlers import HANDLERS, analysis_narrate
from app.agent.handlers.base import HandlerContext
from app.agent.state import AgentState
from app.agent.tool_registry import ToolRegistry
from app.ai.fallback import fallback_reply
from app.schemas.common import TaskType
from tests.conftest import FakeLLM

_STATE = {
    "analysis_year_month": "2026-08",
    "by_verdict": [{"verdict": "ADJUST", "cluster_count": 3, "share": 0.18}],
    "by_category": [
        {"category": "배달", "monthly_total_amount": 96000, "avg_amount": 12000}
    ],
}

# 소수 퍼센트가 나오는 실제 모양 — 3.6%는 근거이고 9.9%는 아니다.
_DECIMAL_STATE = {
    "analysis_year_month": "2026-08",
    "by_verdict": [
        {
            "verdict": "ADJUST",
            "cluster_count": 1,
            "monthly_total_amount": 36000,
            "share": 0.036,
        }
    ],
    "by_category": [
        {"category": "배달", "monthly_total_amount": 36000, "avg_amount": 12000}
    ],
}


def _handle(reply: str, state: dict[str, Any] | None = None):
    fake_llm = FakeLLM(reply=reply)
    context = HandlerContext(
        state=AgentState(
            message="이번 달 특징 알려줘",
            task=TaskType.ANALYSIS_NARRATE,
            structured_state=_STATE if state is None else state,
        ),
        llm=fake_llm,  # type: ignore[arg-type]
        tools=ToolRegistry(),
    )
    return asyncio.run(analysis_narrate.handle(context)), fake_llm


def test_analysis_narrate_is_registered() -> None:
    assert HANDLERS[TaskType.ANALYSIS_NARRATE] is analysis_narrate.handle


def test_sentence_using_only_known_numbers_passes_through() -> None:
    sentence = "배달은 예산의 18%를 차지했고, 96000원이나 썼어요."

    response, fake_llm = _handle(sentence)

    assert response.reply == sentence
    assert response.fallback is False
    assert "share는 그 달 소비액을 월 예산으로 나눈" in fake_llm.calls[0][0]


def test_share_is_checked_as_rounded_percent() -> None:
    """state의 share=0.18은 '18%'로 언급될 수 있다 — 이것도 근거로 인정한다."""

    response, _ = _handle("이 소비는 18%예요.")

    assert response.reply == "이 소비는 18%예요."


def test_invented_number_falls_back_to_deterministic_reply() -> None:
    sentence = "배달에 250000원이나 썼어요."  # state에 없는 금액

    response, _ = _handle(sentence)

    assert response.reply != sentence
    assert response.reply == fallback_reply(TaskType.ANALYSIS_NARRATE, _STATE)
    assert response.fallback is True


def test_verified_sentence_is_not_marked_as_fallback() -> None:
    response, _ = _handle("배달 소비가 가장 눈에 띄었어요.")

    assert response.fallback is False


def test_decimal_percent_from_share_passes() -> None:
    """`share=0.036`은 문장에서 `3.6%`로 나오는 게 정상이다."""

    sentence = "배달은 월 예산의 3.6%를 차지했어요."

    response, _ = _handle(sentence, state=_DECIMAL_STATE)

    assert response.reply == sentence


def test_rounded_percent_from_share_passes() -> None:
    """`3.6%`를 `4%`로 반올려 말하는 것도 근거 안이다."""

    sentence = "배달은 월 예산의 4%를 차지했어요."

    response, _ = _handle(sentence, state=_DECIMAL_STATE)

    assert response.reply == sentence


def test_invented_single_digit_percent_is_rejected() -> None:
    """한 자릿수라도 퍼센트면 서수 예외가 아니라 집계 근거와 대조한다(E-101)."""

    sentence = "배달은 월 예산의 8%를 차지했어요."

    response, _ = _handle(sentence, state=_DECIMAL_STATE)

    assert response.reply == fallback_reply(TaskType.ANALYSIS_NARRATE, _DECIMAL_STATE)
    assert response.fallback is True


def test_spaced_single_digit_percent_is_still_rejected() -> None:
    """`%` 앞 공백으로 한 자릿수 비율 검증을 우회할 수 없다."""

    sentence = "배달은 월 예산의 8 %를 차지했어요."

    response, _ = _handle(sentence, state=_DECIMAL_STATE)

    assert response.reply == fallback_reply(TaskType.ANALYSIS_NARRATE, _DECIMAL_STATE)
    assert response.fallback is True


def test_spaced_known_single_digit_percent_passes() -> None:
    sentence = "배달은 월 예산의 4 %를 차지했어요."

    response, _ = _handle(sentence, state=_DECIMAL_STATE)

    assert response.reply == sentence


def test_invented_decimal_percent_is_rejected() -> None:
    """소수를 쪼개 읽으면 9·9가 한 자리라 그냥 통과하던 구멍이다 (E-79)."""

    response, _ = _handle(
        "배달은 월 예산의 9.9%를 차지했어요.", state=_DECIMAL_STATE
    )

    assert response.reply == fallback_reply(TaskType.ANALYSIS_NARRATE, _DECIMAL_STATE)
    assert response.fallback is True


def test_single_digit_numbers_are_not_flagged() -> None:
    sentence = "이건 그 중 1번째로 신경 쓸 소비예요."

    response, _ = _handle(sentence)

    assert response.reply == sentence


def test_analysis_year_month_numbers_pass_through() -> None:
    sentence = "2026년 8월에는 배달이 예산의 18%를 차지했어요."

    response, _ = _handle(sentence)

    assert response.reply == sentence


def test_analysis_year_month_hyphen_format_passes_through() -> None:
    sentence = "2026-08 기준 배달 소비가 가장 눈에 띄었어요."

    response, _ = _handle(sentence)

    assert response.reply == sentence


def test_invalid_analysis_year_month_is_not_added_to_known_numbers() -> None:
    state = {**_STATE, "analysis_year_month": "2026-13"}
    sentence = "2026년에는 배달 소비가 가장 눈에 띄었어요."

    response, _ = _handle(sentence, state=state)

    assert response.reply == fallback_reply(TaskType.ANALYSIS_NARRATE, state)
    assert response.fallback is True


def test_sentence_without_numbers_passes_through() -> None:
    sentence = "배달 소비가 가장 눈에 띄었어요."

    response, _ = _handle(sentence)

    assert response.reply == sentence


def test_empty_state_rejects_any_multi_digit_number() -> None:
    sentence = "배달에 96000원 썼어요."

    response, _ = _handle(sentence, state={})

    assert response.reply != sentence
    assert response.fallback is True
