"""REFLECTION — 소비 회고를 6단계 대화로 진행한다 (05 §3 · FR-04).

`INTRO → 만족도 → 목적 → 동행인 → 반복의향 → CONFIRM` 순서다. 단계 확정(`step`)과
저장은 Spring 몫이고, 여기서는 **다음에 물을 것**과 **후보값**만 만든다 (E-18).

LLM 호출은 어느 갈래든 **정확히 1회**다. 공감 문장과 질문을 따로 부르면 NFR-04의 6초
예산이 두 배가 된다 — 자연스러운 부분은 추출기가 함께 돌려준 공감 한마디가 맡고,
질문은 폴백과 공유하는 문구를 쓴다.
"""

from dataclasses import replace
from typing import Any

from app.agent.handlers.base import HandlerContext
from app.ai.fallback import REASON_SENTENCES, REFLECTION_QUESTIONS
from app.reflection.extractor import ReflectionExtractor, to_extraction
from app.reflection.schemas import ReflectionExtraction, Satisfaction
from app.reflection.validator import validate
from app.schemas.chat import ChatResponse
from app.schemas.common import ReflectionStep
from app.schemas.tool import ToolName, ToolResult

# 마지막 두 문장은 문체 규칙이다. `build_system_prompt()`가 공통 `SYSTEM_PROMPT` **뒤에**
# 이 지시문을 붙이므로 나중에 붙은 쪽이 이긴다 — 앞의 해요체 규칙만 믿으면 안 된다 (#25와
# 같은 함정). 특히 "돌아보자고"라는 표현이 문체 본보기로 새어 인사가 통째로 반말로 나왔다.
# 실측: 고치기 전 반말 4/4 → 고친 뒤 해요체 6/6. `temperature=0.2`는 0/6으로 효과가 없었다.
INTRO_INSTRUCTION = (
    "회고 대화를 시작하는 첫 인사입니다. 아래 거래 정보와 선정 이유만 사용해서, "
    "이 거래를 함께 돌아보기를 권하는 두 문장 이내의 인사를 만들어 주세요. "
    "선정 이유는 주어진 문장의 뜻 안에서만 설명하고, 주어지지 않은 수치나 이유를 "
    "덧붙이지 마세요. 아직 만족도나 목적을 묻지 마세요. "
    '두 문장 모두 "~요"로 끝나는 해요체로 씁니다. 반말로 끝내지 않습니다.'
)

# 05 `POST /retrospects/chat` — Spring이 다음 step을 고르는 순서와 같아야 한다.
# 순서가 어긋나면 화면의 버튼(step)과 AI의 질문이 서로 다른 항목을 가리킨다.
_STEP_BY_FIELD: tuple[tuple[str, ReflectionStep], ...] = (
    ("satisfaction", ReflectionStep.SATISFACTION),
    ("purpose", ReflectionStep.PURPOSE),
    ("companion", ReflectionStep.COMPANION),
    ("repeat_intention", ReflectionStep.REPEAT),
)


async def handle(ctx: HandlerContext) -> ChatResponse:
    """현재 단계에 맞는 다음 질문과 회고 후보값을 만든다."""

    state = ctx.state.structured_state

    if _step(state) is ReflectionStep.INTRO:
        # 인사에는 후보값을 싣지 않는다. INTRO의 `message`는 Spring이 넣은 고정 문구라
        # 추출할 것이 없고, 빈 후보를 실으면 Spring이 그것을 "네 항목 모두 되물어라"로
        # 옮겨 담아 인사 화면에 선택지가 쏟아진다. `data`가 없으면 Spring은 사용자가
        # 확인한 값을 그대로 유지한다 (05 §3 · `POST /retrospects/chat`).
        return ChatResponse(reply=await _intro_context(ctx).generate(INTRO_INSTRUCTION))

    turn = await ReflectionExtractor(llm_client=ctx.llm).extract(
        ctx.state.message,
        ctx.state.last_question,
    )
    merged = _merge(to_extraction(_confirmed_values(state)), turn.extraction)
    question = REFLECTION_QUESTIONS[_next_step(merged)]

    return _response(f"{turn.ack} {question}", merged)


def _response(reply: str, reflection: ReflectionExtraction) -> ChatResponse:
    """후보값을 05 §3의 `tool_results[reflection].data`에 실어 돌려준다.

    Registry의 `ToolName.REFLECTION`(Spring 회고 목록 조회)을 부르는 것이 **아니다**.
    Spring은 이 자리에서 회고 후보값을 읽어 다음 단계를 정한다. Tool을 부르지 않으므로
    `tool_receipt()`도 거치지 않는다 — 그 함수는 Tool 결과의 `data`를 비우는 쪽이고
    REFLECTION은 거기서도 예외다.
    """

    return ChatResponse(
        reply=reply,
        tool_results=[
            ToolResult(tool_name=ToolName.REFLECTION, data=reflection.model_dump(mode="json"))
        ],
        needs_clarification=reflection.needs_clarification,
    )


def _merge(
    confirmed: ReflectionExtraction, extracted: ReflectionExtraction
) -> ReflectionExtraction:
    """확정값이 추출값을 이긴다 — 사용자가 이미 확인한 값을 덮지 않는다 (FR-04-07)."""

    return validate(
        ReflectionExtraction(
            purpose=confirmed.purpose or extracted.purpose,
            companion=confirmed.companion or extracted.companion,
            satisfaction=(
                confirmed.satisfaction
                if confirmed.satisfaction is not Satisfaction.UNKNOWN
                else extracted.satisfaction
            ),
            repeat_intention=(
                confirmed.repeat_intention
                if confirmed.repeat_intention is not None
                else extracted.repeat_intention
            ),
        )
    )


def _next_step(reflection: ReflectionExtraction) -> ReflectionStep:
    """첫 미확정 항목의 단계를 고른다. 전부 확정이면 CONFIRM이다.

    한 문장에 값이 여러 개 들어오면 미확정이 그만큼 줄어 **단계가 저절로 건너뛰어진다**
    (FR-04-08). `validate()`가 채운 목록을 쓰되 순서는 05 규칙을 따른다 — validator의
    목록 순서는 다르므로 첫 원소를 그대로 쓰면 안 된다.
    """

    for field, step in _STEP_BY_FIELD:
        if field in reflection.uncertain_fields:
            return step
    return ReflectionStep.CONFIRM


def _intro_context(ctx: HandlerContext) -> HandlerContext:
    """INTRO 프롬프트에 들어갈 상태 자체를 거래와 선정 이유 문장으로 좁힌다 (NFR-02).

    `build_system_prompt()`가 `structured_state`를 통째로 붙이므로, 지시문에서만
    문장표로 옮겨서는 `reason_code`가 그 앞줄에 날것으로 실린다. 좁히려면 상태를
    갈아끼워야 한다 — 코드를 모델이 해석하게 두면 폴백일 때와 설명이 달라지고,
    근거에 없는 살이 붙는다.
    """

    state = ctx.state.structured_state
    intro_state = {
        "transaction": _transaction(state),
        "reason": REASON_SENTENCES.get(_text(state.get("reason_code")), ""),
    }
    return replace(
        ctx, state=ctx.state.model_copy(update={"structured_state": intro_state})
    )


def _confirmed_values(state: dict[str, Any]) -> dict[str, Any]:
    """사용자가 이미 확인한 값. 모양이 어긋나면 아무것도 확정되지 않은 것으로 본다."""

    confirmed = state.get("reflection")
    return confirmed if isinstance(confirmed, dict) else {}


def _transaction(state: dict[str, Any]) -> dict[str, Any]:
    """회고 단서로 쓸 거래 값만 꺼낸다 (FR-04-02 — 일시 · 가맹점 · 금액)."""

    transaction = state.get("transaction")
    if not isinstance(transaction, dict):
        return {}

    picked: dict[str, Any] = {}
    for key in ("occurred_at", "merchant", "category", "time_slot"):
        value = _text(transaction.get(key))
        if value:
            picked[key] = value
    amount = transaction.get("amount")
    if isinstance(amount, int | float) and not isinstance(amount, bool):
        picked["amount"] = amount
    return picked


def _step(state: dict[str, Any]) -> ReflectionStep | None:
    """알 수 없는 단계는 임의 해석하지 않는다 — INTRO가 아니면 추출 갈래로 간다."""

    try:
        return ReflectionStep(state.get("step"))
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""
