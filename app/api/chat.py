"""Spring이 호출하는 채팅 API.

HTTP 요청을 DTO로 검증해 Single Agent에 전달하며 도메인 계산은 수행하지 않는다.
"""

from fastapi import APIRouter

from app.agent.agent import SingleAgent
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(tags=["chat"])
agent = SingleAgent()


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """사용자 메시지를 Single Agent에 전달한다."""

    return await agent.run(request)

