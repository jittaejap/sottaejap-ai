"""Task 종류와 Handler를 연결하는 라우팅 표."""

from app.agent.handlers import action_plan, cluster_naming, finance_qa, reflection
from app.agent.handlers.base import Handler
from app.schemas.common import TaskType

HANDLERS: dict[TaskType, Handler] = {
    TaskType.REFLECTION: reflection.handle,
    TaskType.ACTION_PLAN: action_plan.handle,
    TaskType.CLUSTER_NAMING: cluster_naming.handle,
    TaskType.FINANCE_QA: finance_qa.handle,
}
