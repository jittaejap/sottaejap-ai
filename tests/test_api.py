"""FastAPI Endpoint 연결과 X-Internal-Secret 검사 테스트.

`TaskType` 6종이 `/chat`에서 Mock Spring 위로 끝까지 도는지는
`test_chat_*_task_returns_200` 테스트가 확인한다 (#57 · I2). Handler 내부 로직
(숫자 가드 · 문체 규칙 등)은 `tests/test_handler_*.py`가 이미 단위로 확인하므로
여기서는 배선(라우팅 · Mock Spring 응답 · 200/`fallback`)만 본다.
"""

import asyncio
from collections.abc import Callable
from typing import Any

import httpx

from app.agent.agent import SingleAgent
from app.agent.tool_registry import ToolRegistry, build_default_registry
from app.api.chat import get_agent
from app.main import app
from tests.conftest import TEST_SECRET, FakeLLM, SpringClientFactory


async def request(method: str, path: str, **kwargs: object) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


def _chat(
    task_context: dict[str, Any] | None,
    message: str = "질문",
    recent_messages: list[dict[str, str]] | None = None,
) -> httpx.Response:
    body: dict[str, Any] = {"message": message, "user_id": "1", "task_context": task_context}
    if recent_messages is not None:
        body["recent_messages"] = recent_messages
    return asyncio.run(
        request(
            "POST",
            "/chat",
            json=body,
            headers={"X-Internal-Secret": TEST_SECRET},
        )
    )


def _spring_handler(
    routes: dict[str, dict[str, Any]],
) -> Callable[[httpx.Request], httpx.Response]:
    """05 §3 봉투(`{success, data}`)로 경로별 Mock 응답을 돌려준다."""

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "data": routes[req.url.path]})

    return handler


def _chat_with_registry(
    make_client: SpringClientFactory,
    fake_llm: FakeLLM,
    routes: dict[str, dict[str, Any]],
    task_context: dict[str, Any] | None,
    message: str = "질문",
    recent_messages: list[dict[str, str]] | None = None,
) -> httpx.Response:
    spring_client = make_client(_spring_handler(routes))
    registry: ToolRegistry = build_default_registry(spring_client)
    app.dependency_overrides[get_agent] = lambda: SingleAgent(
        tool_registry=registry, llm_client=fake_llm  # type: ignore[arg-type]
    )
    try:
        return _chat(task_context, message, recent_messages)
    finally:
        app.dependency_overrides.clear()


def test_health_is_open() -> None:
    response = asyncio.run(request("GET", "/health"))

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_chat_requires_internal_secret() -> None:
    missing = asyncio.run(request("POST", "/chat", json={"message": "안녕하세요"}))
    wrong = asyncio.run(
        request("POST", "/chat", json={"message": "안녕하세요"}, headers={"X-Internal-Secret": "nope"})
    )

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert missing.json()["detail"]["code"] == "UNAUTHORIZED"


def test_chat_with_secret_returns_reply_and_fallback_flag(
    fake_llm: FakeLLM,
) -> None:
    app.dependency_overrides[get_agent] = lambda: SingleAgent(llm_client=fake_llm)  # type: ignore[arg-type]
    try:
        response = asyncio.run(
            request(
                "POST",
                "/chat",
                json={"message": "안녕하세요", "user_id": "1"},
                headers={"X-Internal-Secret": TEST_SECRET},
            )
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "LLM 응답"
    assert body["fallback"] is False
    assert body["tool_results"] == []


def test_chat_reflection_intro_task_returns_200(
    fake_llm: FakeLLM, make_client: SpringClientFactory
) -> None:
    """REFLECTION의 INTRO 단계는 Tool을 부르지 않고 바로 인사를 만든다 (05 §3)."""

    task_context = {
        "task": "REFLECTION",
        "status": "ACTIVE",
        "state": {
            "transaction": {
                "id": 1043,
                "occurred_at": "2026-08-22T23:10:00+09:00",
                "merchant": "○○배달",
                "amount": 12000,
                "category": "배달",
                "time_slot": "NIGHT",
            },
            "reason_code": "TIMESLOT_OUTLIER",
            "reflection": {
                "satisfaction": "UNKNOWN",
                "purpose": None,
                "companion": None,
                "repeat_intention": None,
            },
            "step": "INTRO",
        },
    }

    response = _chat_with_registry(
        make_client, fake_llm, {}, task_context, message="회고를 시작할게요"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "LLM 응답"
    assert body["fallback"] is False


def test_chat_reflection_satisfaction_step_fills_tool_results_data(
    make_client: SpringClientFactory,
) -> None:
    """05 §3이 계약으로 못박은 유일한 `tool_results[].data` 자리를 확인한다.

    INTRO만으로는 `_response()`가 만드는 회고 후보값(표준 태그 또는 `null`, E-20)이
    한 번도 검사되지 않는다 — 다음 단계(SATISFACTION)를 하나 더 불러 채운다.
    """

    llm = FakeLLM(json_reply={"satisfaction": "LOW", "ack": "배가 고프면 그럴 수 있어요."})
    task_context = {
        "task": "REFLECTION",
        "status": "ACTIVE",
        "state": {
            "transaction": {
                "id": 1043,
                "occurred_at": "2026-08-22T23:10:00+09:00",
                "merchant": "○○배달",
                "amount": 12000,
                "category": "배달",
                "time_slot": "NIGHT",
            },
            "reason_code": "TIMESLOT_OUTLIER",
            "reflection": {
                "satisfaction": "UNKNOWN",
                "purpose": None,
                "companion": None,
                "repeat_intention": None,
            },
            "step": "SATISFACTION",
        },
    }

    response = _chat_with_registry(
        make_client,
        llm,
        {},
        task_context,
        message="그냥 배고파서 혼자 시켰어요",
        recent_messages=[{"role": "assistant", "content": "이 소비, 만족하셨나요?"}],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["tool_results"][0]["tool_name"] == "reflection"
    data = body["tool_results"][0]["data"]
    assert data["satisfaction"] == "LOW"
    assert data["purpose"] is None
    assert data["companion"] is None


def test_chat_action_plan_task_returns_200(
    fake_llm: FakeLLM, make_client: SpringClientFactory
) -> None:
    task_context = {"task": "ACTION_PLAN", "status": "ACTIVE", "state": {"suggestion_ids": [7]}}
    routes = {
        "/internal/ai/users/1/suggestions": {
            "suggestions": [
                {
                    "id": 7,
                    "behaviorId": 70,
                    "behaviorName": "심야 배달",
                    "monthlyTotalAmount": 96000,
                    "avgAmount": 24000,
                    "txCount": 4,
                    "adjustedSatisfaction": -0.42,
                    "quadrant": "PRIORITY",
                    "adjustCount": 4,
                    "expectedSaving": 96000,
                    "goalId": 3,
                    "status": "PROPOSED",
                    "reason": (
                        "심야 배달의 이번 달 지출이 96,000원이에요. 부담이 컸고 "
                        "만족도도 낮았어요. 횟수를 줄여볼까요?"
                    ),
                }
            ]
        }
    }

    response = _chat_with_registry(make_client, fake_llm, routes, task_context)

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "LLM 응답"
    assert body["fallback"] is False
    # Mock Spring 라우트가 실제로 불려 Handler를 탔다는 증거 — 안 그러면 일반
    # 경로(HANDLERS 미등록 시 폴백 아님)도 같은 200·reply·fallback을 준다.
    assert [r["tool_name"] for r in body["tool_results"]] == ["action_plan"]
    assert body["tool_results"][0]["success"] is True
    assert body["tool_results"][0]["data"] is None


def test_chat_analysis_task_returns_200(
    fake_llm: FakeLLM, make_client: SpringClientFactory
) -> None:
    task_context = {
        "task": "ANALYSIS",
        "status": "ACTIVE",
        "state": {"analysis_year_month": "2026-08"},
    }
    routes = {
        "/internal/ai/users/1/analysis": {
            "analysisYearMonth": "2026-08",
            "byVerdict": [
                {"verdict": "SUSTAIN", "clusterCount": 5, "monthlyTotalAmount": 430000, "share": 0.36},
                {"verdict": "ADJUST", "clusterCount": 3, "monthlyTotalAmount": 210000, "share": 0.18},
            ],
            "pending": {"clusterCount": 7, "monthlyTotalAmount": 180000, "share": 0.15},
            "byCategory": [
                {
                    "category": "배달",
                    "dominantTimeSlot": "NIGHT",
                    "avgAmount": 12000,
                    "monthlyTotalAmount": 96000,
                    "verdict": "ADJUST",
                }
            ],
            "points": [{"x": 1, "y": 2}],
        }
    }

    response = _chat_with_registry(make_client, fake_llm, routes, task_context)

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "LLM 응답"
    assert body["fallback"] is False
    assert [r["tool_name"] for r in body["tool_results"]] == ["analysis"]
    assert body["tool_results"][0]["success"] is True
    assert body["tool_results"][0]["data"] is None


def test_chat_analysis_narrate_task_returns_200(
    fake_llm: FakeLLM, make_client: SpringClientFactory
) -> None:
    """ANALYSIS_NARRATE는 별도 Tool 호출 없이 `state` 값만으로 문장을 만든다 (05 §3)."""

    task_context = {
        "task": "ANALYSIS_NARRATE",
        "status": "ACTIVE",
        "state": {
            "analysis_year_month": "2026-08",
            "by_verdict": [
                {"verdict": "SUSTAIN", "cluster_count": 5, "monthly_total_amount": 430000, "share": 0.36}
            ],
            "by_category": [
                {
                    "category": "배달",
                    "dominant_time_slot": "NIGHT",
                    "avg_amount": 12000,
                    "monthly_total_amount": 96000,
                    "verdict": "ADJUST",
                }
            ],
        },
    }

    response = _chat_with_registry(make_client, fake_llm, {}, task_context)

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "LLM 응답"
    assert body["fallback"] is False


def test_chat_cluster_naming_task_returns_200(
    fake_llm: FakeLLM, make_client: SpringClientFactory
) -> None:
    task_context = {
        "task": "CLUSTER_NAMING",
        "status": "ACTIVE",
        "state": {
            "cluster_key": "배달|NIGHT||",
            "sample_merchants": ["○○배달"],
            "tx_count": 5,
        },
    }

    response = _chat_with_registry(make_client, fake_llm, {}, task_context)

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "LLM 응답"
    assert body["fallback"] is False


def test_chat_finance_qa_task_returns_200(
    fake_llm: FakeLLM, make_client: SpringClientFactory
) -> None:
    """`FINANCIAL_RAG`는 `DATABASE_URL`이 있을 때만 등록된다 — 테스트 Registry에는

    없으므로 근거 없음 경로로 내려가지만, 그래도 200이어야 한다 (FR-12-02).
    """

    task_context = {"task": "FINANCE_QA", "status": "ACTIVE", "state": {}}

    response = _chat_with_registry(
        make_client, fake_llm, {}, task_context, message="예금자보호 한도가 얼마예요?"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "LLM 응답"
    assert body["fallback"] is False
    # FINANCIAL_RAG가 미등록이라 실패 영수증이 남는다 — 이 실패 자체가 근거 없음
    # 경로를 실제로 탔다는 증거다(call_tool이 KeyError를 success=False로 흡수).
    assert body["tool_results"][0]["tool_name"] == "financial_rag"
    assert body["tool_results"][0]["success"] is False


def test_chat_cluster_naming_falls_back_when_llm_unavailable() -> None:
    """Tool을 안 부르는 경로에서도 LLM 실패는 200 + `fallback: true`다 (FR-04-15)."""

    failing_llm = FakeLLM(reply=None)
    task_context = {
        "task": "CLUSTER_NAMING",
        "status": "ACTIVE",
        "state": {"cluster_key": "배달|NIGHT||", "sample_merchants": [], "tx_count": 1},
    }

    app.dependency_overrides[get_agent] = lambda: SingleAgent(llm_client=failing_llm)  # type: ignore[arg-type]
    try:
        response = _chat(task_context)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["fallback"] is True
    assert body["reply"]


def test_chat_analysis_falls_back_when_llm_unavailable(
    make_client: SpringClientFactory,
) -> None:
    """Tool을 부르는 경로도 LLM 실패는 폴백으로 흡수된다 — Spring 조회는 이미 끝난 뒤다."""

    failing_llm = FakeLLM(reply=None)
    task_context = {
        "task": "ANALYSIS",
        "status": "ACTIVE",
        "state": {"analysis_year_month": "2026-08"},
    }
    routes = {
        "/internal/ai/users/1/analysis": {
            "analysisYearMonth": "2026-08",
            "byVerdict": [
                {"verdict": "SUSTAIN", "clusterCount": 5, "monthlyTotalAmount": 430000, "share": 0.36},
                {"verdict": "ADJUST", "clusterCount": 3, "monthlyTotalAmount": 210000, "share": 0.18},
            ],
            "pending": {"clusterCount": 7, "monthlyTotalAmount": 180000, "share": 0.15},
            "byCategory": [
                {
                    "category": "배달",
                    "dominantTimeSlot": "NIGHT",
                    "avgAmount": 12000,
                    "monthlyTotalAmount": 96000,
                    "verdict": "ADJUST",
                }
            ],
            "points": [{"x": 1, "y": 2}],
        }
    }

    response = _chat_with_registry(make_client, failing_llm, routes, task_context)

    assert response.status_code == 200
    body = response.json()
    assert body["fallback"] is True
    assert body["reply"]
