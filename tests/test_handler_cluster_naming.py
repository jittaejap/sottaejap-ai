"""CLUSTER_NAMING Handler가 소비 묶음 이름 계약을 지키는지 확인한다."""

import asyncio
from typing import Any

from app.agent.handlers import HANDLERS, cluster_naming
from app.agent.handlers.base import HandlerContext
from app.agent.state import AgentState
from app.agent.tool_registry import ToolRegistry
from app.ai.fallback import CLUSTER_NAME_MAX_LENGTH
from app.schemas.common import TaskType
from tests.conftest import FakeLLM


def _context(fake_llm: FakeLLM, state: dict[str, Any]) -> HandlerContext:
    return HandlerContext(
        state=AgentState(
            message="이 소비 묶음의 이름을 지어주세요.",
            structured_state=state,
        ),
        llm=fake_llm,  # type: ignore[arg-type]
        tools=ToolRegistry(),
    )


def test_cluster_naming_is_registered() -> None:
    assert HANDLERS[TaskType.CLUSTER_NAMING] is cluster_naming.handle


def test_cluster_naming_returns_llm_reply_when_within_length(
    fake_llm: FakeLLM,
) -> None:
    fake_llm.reply = "스벅단골"
    context = _context(
        fake_llm,
        {
            "cluster_key": "배달|NIGHT|스트레스 해소|혼자",
            "sample_merchants": ["스타벅스"],
            "tx_count": 5,
        },
    )

    response = asyncio.run(cluster_naming.handle(context))

    assert response.reply == "스벅단골"
    instruction = fake_llm.calls[0][0]
    assert "카테고리|시간대|목적|동행인" in instruction
    assert "배달|NIGHT|스트레스 해소|혼자" in instruction
    assert "스타벅스" in instruction
    assert response.tool_results == []


def test_cluster_naming_trims_reply_over_12_chars(fake_llm: FakeLLM) -> None:
    original = "이것은열두글자가넘는이름입니다"
    fake_llm.reply = original

    response = asyncio.run(
        cluster_naming.handle(_context(fake_llm, {"cluster_key": "카페|오전|업무|혼자"}))
    )

    assert len(response.reply) <= CLUSTER_NAME_MAX_LENGTH
    assert response.reply == original[:CLUSTER_NAME_MAX_LENGTH]


def test_cluster_naming_uses_first_line_and_removes_quotes(
    fake_llm: FakeLLM,
) -> None:
    replies = (
        '  “스벅단골”\n이 이름을 추천합니다.  ',
        "스벅단골\r\n이 이름을 추천합니다.",
        "스벅단골\t\n이 이름을 추천합니다.",
        "스벅단골\xa0\n이 이름을 추천합니다.",
        "‘스벅단골’",
        "「스벅단골」",
        "“ 스벅단골 ”",
    )

    for reply in replies:
        fake_llm.reply = reply
        response = asyncio.run(
            cluster_naming.handle(_context(fake_llm, {"cluster_key": "카페|오전|업무|혼자"}))
        )

        assert response.reply == "스벅단골"


def test_cluster_naming_preserves_blank_reply_for_spring_fallback(
    fake_llm: FakeLLM,
) -> None:
    fake_llm.reply = "   "
    context = _context(fake_llm, {"sample_merchants": ["교촌치킨"]})

    response = asyncio.run(cluster_naming.handle(context))

    assert response.reply == ""


def test_cluster_naming_skips_llm_when_no_signal(fake_llm: FakeLLM) -> None:
    """cluster_key·sample_merchants가 둘 다 비면 LLM을 부르지 않고 결정론적 이름을 낸다.

    실제 LLM으로 재현됨: 이 상태에서 LLM을 부르면 "이름만 답하라"는 지시를 어기고
    SYSTEM_PROMPT few-shot 예시를 본뜬 문장을 냈고, reply[:12]가 그걸 단어 중간에서
    잘라 "확인된 근거가 없어 지" 같은 조각이 나갔다(5/5 재현).
    """

    from app.ai.fallback import fallback_reply

    context = _context(fake_llm, {})

    response = asyncio.run(cluster_naming.handle(context))

    assert response.reply == fallback_reply(TaskType.CLUSTER_NAMING, {})
    assert fake_llm.calls == []
    assert response.fallback is False


def test_cluster_naming_treats_whitespace_only_values_as_absent(fake_llm: FakeLLM) -> None:
    """PR #63 리뷰 지적 — 공백만 있는 값은 문자열 타입 검사만으로는 안 걸러진다.

    수정 전에는 {"cluster_key": "   "}나 {"sample_merchants": ["   "]}가 "빈 입력"
    판정을 피해 그대로 LLM을 불렀고, 모델 입장에서는 진짜 빈 입력과 다를 게 없어
    같은 문장 잘림 사고가 재현될 수 있었다.
    """

    from app.ai.fallback import fallback_reply

    cases = (
        {"cluster_key": "   "},
        {"sample_merchants": ["   "]},
        {"sample_merchants": [""]},
        {"cluster_key": "  ", "sample_merchants": ["   ", ""]},
    )
    for state in cases:
        context = _context(fake_llm, state)

        response = asyncio.run(cluster_naming.handle(context))

        assert response.reply == fallback_reply(TaskType.CLUSTER_NAMING, state)
        assert fake_llm.calls == []


def test_cluster_naming_calls_llm_when_only_merchants_present(fake_llm: FakeLLM) -> None:
    """cluster_key가 비어도 sample_merchants가 있으면 정상적으로 LLM을 부른다."""

    fake_llm.reply = "교촌단골"
    context = _context(fake_llm, {"sample_merchants": ["교촌치킨"]})

    response = asyncio.run(cluster_naming.handle(context))

    assert response.reply == "교촌단골"
    assert len(fake_llm.calls) == 1


def test_cluster_naming_replaces_malformed_state_with_defaults(
    fake_llm: FakeLLM,
) -> None:
    fake_llm.reply = "기본묶음"
    context = _context(
        fake_llm,
        {
            "cluster_key": 123,
            "sample_merchants": ["스타벅스", 456],
            "tx_count": True,
        },
    )

    response = asyncio.run(cluster_naming.handle(context))

    assert response.reply == "기본묶음"
    instruction = fake_llm.calls[0][0]
    assert '"cluster_key": ""' in instruction
    assert '"sample_merchants": ["스타벅스"]' in instruction
    assert '"tx_count": 0' in instruction
