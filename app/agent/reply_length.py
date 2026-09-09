"""`/chat` `reply` 길이 상한 (05 §2 #11·#28 · E-109·E-110 · #55).

client가 `reply`를 그대로 `recentMessages`(assistant 항목)에 실어 되돌려 보내는데,
server가 그 항목에 2,000자 상한을 걸고 넘으면 400 `INVALID_INPUT`을 낸다(server PR
#59). 만드는 쪽(AI)이 넘기지 않을 책임을 진다 — `LLMClient.generate`의 `max_tokens`
(`app/core/llm.py`)는 폭주를 막는 값일 뿐 2,000자를 보장하지 못해, `SingleAgent`가
`ChatResponse`를 돌려주기 직전에 여기서 한 번 더 자른다.
"""

import re

MAX_REPLY_LENGTH = 2000

# 해요체 어미("~요") 뒤에 붙는 문장부호에서만 자른다 — 아무 위치에서나 자르면
# 어미가 깨져 문장이 반말처럼 읽힌다(E-90 · #46과 같은 톤 규칙).
_SENTENCE_BOUNDARY = re.compile(r"(?<=요)[.!?~]")


def truncate_reply(reply: str, max_length: int = MAX_REPLY_LENGTH) -> str:
    """길이 상한(코드 포인트 기준)을 넘으면 마지막 해요체 문장 경계에서 자른다.

    경계가 창 앞쪽 절반 안에만 있으면 그 경계로는 안 자른다 — 뒤 내용 대부분을
    버리는 게 하드컷보다 나쁘다("짧아요." + 2,500자 한 문장 → 4자만 남는 사례).
    상한 안에 쓸 만한 경계가 없으면(극단적으로 긴 한 문장) 그대로 하드컷한다 —
    상한을 지키는 쪽이 문장 완결성보다 우선이다.
    """

    if len(reply) <= max_length:
        return reply

    window = reply[:max_length]
    boundaries = list(_SENTENCE_BOUNDARY.finditer(window))
    if boundaries and boundaries[-1].end() >= max_length // 2:
        return window[: boundaries[-1].end()]
    return window
