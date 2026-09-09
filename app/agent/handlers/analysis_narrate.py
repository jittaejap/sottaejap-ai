"""ANALYSIS_NARRATE — '나만의 특징' 한 문장을 만든다 (05 §3 · FR-11-03).

`GET /analysis`가 화면에 보여줄 `highlight`를 그 자리에서 만들기 위해 부르는
Task다(05 §2). `state.by_verdict[]` · `by_category[]`만으로 문장을 만들고
별도 Tool 호출은 없다 — `ctx.generate()`가 `structured_state`를 프롬프트에
이미 실어 보낸다(`app/agent/prompt.py`).

프롬프트 지시만으로는 근거 밖 숫자를 100% 못 막는다(NFR-02) — 그래서 생성된
문장의 숫자를 `state`에 실제로 있는 값과 대조하는 가드레일을 코드로 한 번 더
건다. 하나라도 근거에 없으면 LLM 문장을 버리고 `app/ai/fallback.py`의
결정론적 폴백으로 바꾼다. 이때 `fallback=True`를 세우는 건 LLM 장애가 아니라
"정상 응답을 검증에서 버렸다"는 상태 표시다 — Spring이 이 플래그를 보고
자기 템플릿으로 갈음한다(E-75 · 06 R19).
"""

import re

from app.agent.handlers.base import HandlerContext
from app.ai.fallback import fallback_reply
from app.schemas.chat import ChatResponse
from app.schemas.common import TaskType

INSTRUCTION = (
    "아래 집계 데이터만 근거로 '나만의 특징'을 한 문장으로 요약하세요. "
    "데이터에 없는 숫자나 판단을 지어내지 마세요. 수치는 데이터에 있는 값 "
    "그대로 씁니다.\n"
    # share의 분모는 월 예산이다(05 §2 · E-73). 명시 안 하면 모델이 "전체
    # 소비 대비"로 바꿔 말하는 실측 오류가 있었다 — 분모를 문장으로 못박는다.
    "share는 그 달 소비액을 월 예산으로 나눈 비율입니다. '전체 소비의 몇 %'처럼 "
    "다른 분모로 바꿔 말하지 마세요.\n"
    "verdict는 SUSTAIN이면 '지켜도 좋은 소비', ADJUST면 '바꿔볼 소비'입니다."
)

# 소수점을 한 덩어리로 잡는다. "3.6%"를 "3"·"6"으로 쪼개면 둘 다 한 자리라
# 아래 서수 예외에 걸려 검사 없이 통과한다 — 지어낸 "9.9%"가 그 구멍으로 샜다(E-79).
_NUMBER_PATTERN = re.compile(r"\d[\d,]*(?:\.\d+)?")

# 근거 값과 문장 속 값을 견줄 때 허용하는 오차.
_TOLERANCE = 0.05


async def handle(ctx: HandlerContext) -> ChatResponse:
    """집계 근거로 한 문장을 만들고, 근거 밖 숫자가 있으면 폴백으로 바꾼다."""

    sentence = await ctx.generate(INSTRUCTION)

    if _has_unverified_number(sentence, _known_numbers(ctx.state.structured_state)):
        return ChatResponse(
            reply=fallback_reply(TaskType.ANALYSIS_NARRATE, ctx.state.structured_state),
            fallback=True,
        )

    return ChatResponse(reply=sentence)


def _known_numbers(state: dict) -> set[float]:
    """`by_verdict`·`by_category`에 실제로 있는 수치만 허용 목록으로 만든다.

    비율(`share`)은 문장에서 퍼센트로 나오므로 100배 한 값도 넣는다. 소수
    그대로(`3.6`)와 반올림한 정수(`4`) 둘 다 자연스러운 표기라 함께 허용한다.
    """

    numbers: set[float] = set()
    for group in ("by_verdict", "by_category"):
        items = state.get(group)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            for key, value in item.items():
                if isinstance(value, bool) or not isinstance(value, int | float):
                    continue
                numbers.add(float(value))
                if key == "share" and 0 <= value <= 1:
                    numbers.add(value * 100)
                    numbers.add(float(round(value * 100)))
    return numbers


def _has_unverified_number(sentence: str, known: set[float]) -> bool:
    """문장에 등장한 숫자 중 근거에 없는 게 있으면 True다.

    한 자리 정수는 건너뛴다 — "가장", "제일" 같은 서수 표현에 섞여 나올 수
    있어서다. 소수는 한 자리라도 검사한다. 퍼센트가 소수로 나오는 게 정상
    경로이고(`share=0.036` → `3.6%`), 거기를 비워 두면 지어낸 비율이 그대로
    나간다.
    """

    for match in _NUMBER_PATTERN.findall(sentence):
        text = match.replace(",", "")
        if "." not in text and len(text) < 2:
            continue
        value = float(text)
        if not any(abs(value - candidate) < _TOLERANCE for candidate in known):
            return True
    return False
