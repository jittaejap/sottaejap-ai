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

    response = asyncio.run(cluster_naming.handle(_context(fake_llm, {})))

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
        response = asyncio.run(cluster_naming.handle(_context(fake_llm, {})))

        assert response.reply == "스벅단골"


def test_cluster_naming_preserves_blank_reply_for_spring_fallback(
    fake_llm: FakeLLM,
) -> None:
    fake_llm.reply = "   "
    context = _context(fake_llm, {"sample_merchants": ["교촌치킨"]})

    response = asyncio.run(cluster_naming.handle(context))

    assert response.reply == ""


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
