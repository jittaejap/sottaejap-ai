"""Spring이 호출하는 채팅 API.

HTTP 요청을 DTO로 검증해 Single Agent에 전달하며 도메인 계산은 수행하지 않는다.
`X-Internal-Secret` 헤더가 `INTERNAL_SHARED_SECRET`과 다르면 401이다 (05 §3).
시크릿이 비어 있으면 Spring 쪽 규칙과 같이 모든 요청을 거부한다.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.agent.agent import SingleAgent
from app.core.config import get_settings
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(tags=["chat"])
_agent = SingleAgent()


def get_agent() -> SingleAgent:
    """테스트에서 교체할 수 있도록 Agent를 의존성으로 노출한다."""

    return _agent


def require_internal_secret(
    x_internal_secret: Annotated[str | None, Header()] = None,
) -> None:
    """Spring → AI 호출의 공유 시크릿을 검사한다."""

    expected = get_settings().internal_shared_secret
    if not expected or x_internal_secret != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "X-Internal-Secret이 없거나 다릅니다."},
        )


@router.post(
    "/chat",
    response_model=ChatResponse,
    dependencies=[Depends(require_internal_secret)],
)
async def chat(
    request: ChatRequest,
    agent: Annotated[SingleAgent, Depends(get_agent)],
) -> ChatResponse:
    """사용자 메시지를 Single Agent에 전달한다."""

    return await agent.run(request)
