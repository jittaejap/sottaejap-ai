"""소때잡 FastAPI 애플리케이션 진입점."""

from fastapi import FastAPI

from app.api.chat import router as chat_router
from app.schemas.common import HealthResponse

app = FastAPI(
    title="소때잡 AI Server",
    description="Single Agent, Tool Calling, 회고 구조화, 금융 RAG를 위한 AI 서버",
    version="0.1.0",
)
app.include_router(chat_router)


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    """프로세스가 요청을 받을 수 있는지 확인한다."""

    return HealthResponse()

