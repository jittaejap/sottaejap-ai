"""Task 종류와 Handler를 연결하는 라우팅 표."""

from app.agent.handlers.base import Handler
from app.schemas.common import TaskType

HANDLERS: dict[TaskType, Handler] = {}
