"""LLM 폴백 템플릿이 작업·단계별로 문서(05 §3) 규칙을 지키는지 확인한다."""

from app.ai.fallback import CLUSTER_NAME_MAX_LENGTH, DEFAULT_REPLY, fallback_reply
from app.schemas.common import TaskType

TRANSACTION = {"merchant": "○○배달", "amount": 12000, "category": "배달", "time_slot": "NIGHT"}


def test_reflection_intro_uses_reason_code_and_transaction() -> None:
    reply = fallback_reply(
        TaskType.REFLECTION,
        {"step": "INTRO", "reason_code": "TIMESLOT_OUTLIER", "transaction": TRANSACTION},
    )

    assert reply == "○○배달에서 12,000원을 쓰셨네요. 평소와 다른 시간대의 소비였어요. 이 소비를 함께 돌아볼까요?"


def test_reflection_intro_without_transaction_still_answers() -> None:
    reply = fallback_reply(TaskType.REFLECTION, {"step": "INTRO", "reason_code": "UNKNOWN_CODE"})

    assert reply == "최근 소비 하나를 함께 돌아볼까요?"


def test_reflection_steps_have_questions() -> None:
    for step in ("SATISFACTION", "PURPOSE", "COMPANION", "REPEAT", "CONFIRM"):
        assert fallback_reply(TaskType.REFLECTION, {"step": step})


def test_cluster_naming_is_within_twelve_characters() -> None:
    name = fallback_reply(
        TaskType.CLUSTER_NAMING,
        {"cluster_key": "배달|NIGHT", "sample_merchants": ["아주아주아주긴가맹점이름입니다"], "tx_count": 4},
    )

    assert 0 < len(name) <= CLUSTER_NAME_MAX_LENGTH
    assert fallback_reply(TaskType.CLUSTER_NAMING, {}) == "반복 소비 묶음"


def test_analysis_narrate_has_no_digits() -> None:
    reply = fallback_reply(TaskType.ANALYSIS_NARRATE, {"by_verdict": [], "by_category": []})

    assert not any(ch.isdigit() for ch in reply)


def test_unknown_task_returns_default() -> None:
    assert fallback_reply(None, {}) == DEFAULT_REPLY
