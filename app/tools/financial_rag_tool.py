"""금융 지식 검색 Tool.

Tool 중 유일하게 Python 내부 RAG 모듈을 호출하며 금융 답변의 근거 Chunk를 반환한다.
"""

from app.rag.retriever import FinancialRetriever
from app.schemas.tool import ToolName, ToolResult


class FinancialRagTool:
    """금융 검색 인터페이스를 Agent Tool 형태로 노출한다."""

    def __init__(self, retriever: FinancialRetriever) -> None:
        self._retriever = retriever

    async def execute(self, query: str, top_k: int = 5) -> ToolResult:
        results = await self._retriever.search(query=query, top_k=top_k)
        return ToolResult(
            tool_name=ToolName.FINANCIAL_RAG,
            data=[result.model_dump(mode="json") for result in results],
        )

