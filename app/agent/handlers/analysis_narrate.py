"""ANALYSIS_NARRATE — '나만의 특징' 한 문장을 만든다 (05 §3 · FR-11-03).

`GET /analysis`가 화면에 보여줄 `highlight`를 그 자리에서 만들기 위해 부르는
Task다(05 §2). `state.by_verdict[]` · `by_category[]`만으로 문장을 만들고
별도 Tool 호출은 없다 — `ctx.generate()`가 `structured_state`를 프롬프트에
이미 실어 보낸다(`app/agent/prompt.py`).

숫자 검증은 `app/agent/handlers/number_guard.py`를 쓴다 — `ANALYSIS`(#48)와
공유한다. 하나라도 근거에 없으면 LLM 문장을 버리고 `app/ai/fallback.py`의
결정론적 폴백으로 바꾼다. 이때 `fallback=True`를 세우는 건 LLM 장애가 아니라
"정상 응답을 검증에서 버렸다"는 상태 표시다 — Spring이 이 플래그를 보고
자기 템플릿으로 갈음한다(E-75 · 06 R19).
"""

from app.agent.handlers.base import HandlerContext
from app.agent.handlers.number_guard import (
    has_unverified_number,
    known_numbers,
    known_percentages,
)
from app.agent.prompt import HAEYO_RULE
from app.ai.fallback import fallback_reply
from app.schemas.chat import ChatResponse
from app.schemas.common import TaskType

# 공통 SYSTEM_PROMPT의 해요체 규칙만 믿지 않는다 — Task 지시문이 나중에 붙어
# 이기므로 여기서도 직접 못박는다 (#40·#46·#48과 같은 함정). 실측(합성 시나리오
# 6개, #60)으로 8문장 중 5개(62.5%)가 반말이었던 게 확인됐다.
INSTRUCTION = (
    "아래 집계 데이터만 근거로 '나만의 특징'을 한 문장으로 요약하세요. "
    "데이터에 없는 숫자나 판단을 지어내지 마세요. 수치는 데이터에 있는 값 "
    "그대로 씁니다.\n"
    # share의 분모는 월 예산이다(05 §2 · E-73). 명시 안 하면 모델이 "전체
    # 소비 대비"로 바꿔 말하는 실측 오류가 있었다 — 분모를 문장으로 못박는다.
    "share는 그 달 소비액을 월 예산으로 나눈 비율입니다. '전체 소비의 몇 %'처럼 "
    "다른 분모로 바꿔 말하지 마세요.\n"
    "verdict는 SUSTAIN이면 '지켜도 좋은 소비', ADJUST면 '바꿔볼 소비'입니다.\n"
    f"{HAEYO_RULE}"
)


async def handle(ctx: HandlerContext) -> ChatResponse:
    """집계 근거로 한 문장을 만들고, 근거 밖 숫자가 있으면 폴백으로 바꾼다."""

    sentence = await ctx.generate(INSTRUCTION)
    state = ctx.state.structured_state
    groups = [state.get("by_verdict"), state.get("by_category")]

    if has_unverified_number(
        sentence,
        known_numbers(groups, year_month=state.get("analysis_year_month")),
        known_percentages=known_percentages(groups),
    ):
        return ChatResponse(
            reply=fallback_reply(TaskType.ANALYSIS_NARRATE, state),
            fallback=True,
        )

    return ChatResponse(reply=sentence)
