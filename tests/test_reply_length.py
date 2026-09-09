"""`truncate_reply()`가 2,000자 상한을 해요체 문장 경계에서 지키는지 확인한다 (#55)."""

from app.agent.reply_length import MAX_REPLY_LENGTH, truncate_reply


def test_short_reply_is_unchanged() -> None:
    reply = "배달에 12,000원을 쓰셨어요."

    assert truncate_reply(reply) == reply


def test_reply_at_exact_limit_is_unchanged() -> None:
    reply = "가" * (MAX_REPLY_LENGTH - 2) + "요."

    assert len(reply) == MAX_REPLY_LENGTH
    assert truncate_reply(reply) == reply


def test_long_reply_is_cut_at_last_polite_sentence_boundary() -> None:
    first = "가" * 50 + "요."
    second = "나" * (MAX_REPLY_LENGTH - len(first) - 2) + "요."
    third = "다" * 200 + "요."
    reply = first + second + third
    assert len(first + second) == MAX_REPLY_LENGTH

    result = truncate_reply(reply)

    assert len(result) <= MAX_REPLY_LENGTH
    assert result == first + second
    assert result.endswith("요.")


def test_long_reply_without_boundary_in_window_is_hard_cut() -> None:
    reply = "가" * (MAX_REPLY_LENGTH + 500)

    result = truncate_reply(reply)

    assert len(result) == MAX_REPLY_LENGTH


def test_boundary_only_in_front_half_is_hard_cut_instead() -> None:
    """경계가 창 앞쪽에만 있으면 그 경계로 안 자른다 — 대부분을 버리는 게

    하드컷보다 나쁘다 ("짧아요." + 긴 한 문장 → 4자만 남는 사례, 리뷰 반영).
    """

    reply = "짧아요." + "가" * (MAX_REPLY_LENGTH + 500)

    result = truncate_reply(reply)

    assert len(result) == MAX_REPLY_LENGTH
    assert result != "짧아요."


def test_boundary_accepts_exclamation_question_and_tilde() -> None:
    for mark in ("!", "?", "~"):
        first = "가" * (MAX_REPLY_LENGTH - 102) + f"요{mark}"
        reply = first + "나" * 100 + f"요{mark}"
        assert len(first) < MAX_REPLY_LENGTH

        result = truncate_reply(reply)

        assert result == first
        assert result.endswith(f"요{mark}")
