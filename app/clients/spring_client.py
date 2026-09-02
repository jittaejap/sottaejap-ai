"""Spring 내부 AI API 호출을 전담하는 HTTP Client (05 §3 · 06 R5).

Tool은 이 Client의 도메인 메서드만 사용한다. 경로 6종은 05 §3 표와 1:1이다.
인증은 `X-Internal-Secret` 헤더 하나이고, 응답 봉투 `{ success, data | error }`는
여기서 벗겨 `data`만 돌려준다. camelCase 키는 변환하지 않는다.
"""

from typing import Any

import httpx

from app.core.config import Settings, get_settings

INTERNAL_SECRET_HEADER = "X-Internal-Secret"


class SpringApiError(RuntimeError):
    """Spring이 `success: false`를 돌려준 경우. `code`는 05 §0 오류 코드다."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class SpringClient:
    """Spring Boot 내부 AI API에 접근하는 유일한 Client."""

    def __init__(
        self,
        settings: Settings | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._owns_client = http_client is None
        headers = {}
        if self._settings.internal_shared_secret:
            headers[INTERNAL_SECRET_HEADER] = self._settings.internal_shared_secret
        self._http = http_client or httpx.AsyncClient(
            base_url=self._settings.spring_base_url,
            timeout=self._settings.spring_timeout_seconds,
            headers=headers,
        )

    async def close(self) -> None:
        """내부에서 생성한 HTTP 연결을 닫는다."""

        if self._owns_client:
            await self._http.aclose()

    async def __aenter__(self) -> "SpringClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Endpoint를 호출하고 봉투를 벗긴 `data`를 반환한다."""

        response = await self._http.request(method, endpoint, **kwargs)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or "success" not in payload:
            raise ValueError("Spring API 응답은 { success, data } 봉투여야 합니다.")
        if not payload["success"]:
            error = payload.get("error") or {}
            raise SpringApiError(
                str(error.get("code", "UNKNOWN")), str(error.get("message", ""))
            )
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ValueError("Spring API `data`는 JSON object여야 합니다.")
        return data

    async def get_transactions(
        self, user_id: str, query: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """거래 조회. query 키: from · to · category · size."""

        return await self._request(
            "GET", f"/internal/ai/users/{user_id}/transactions", params=query
        )

    async def get_reflections(self, user_id: str) -> dict[str, Any]:
        """회고 조회."""

        return await self._request("GET", f"/internal/ai/users/{user_id}/reflections")

    async def save_reflection(
        self, user_id: str, reflection: dict[str, Any]
    ) -> dict[str, Any]:
        """사용자 확인이 끝난 회고만 저장한다. 본문은 snake_case로 보낸다."""

        return await self._request(
            "POST", f"/internal/ai/users/{user_id}/reflections", json=reflection
        )

    async def get_behavior_analysis(self, user_id: str) -> dict[str, Any]:
        """Spring 규칙 엔진의 소비 분석 결과와 만족도 지도 points를 조회한다."""

        return await self._request("GET", f"/internal/ai/users/{user_id}/analysis")

    async def get_action_plan(self, user_id: str) -> dict[str, Any]:
        """Spring이 계산한 행동 조정 제안과 예상 절감 결과를 조회한다."""

        return await self._request("GET", f"/internal/ai/users/{user_id}/suggestions")

    async def get_memory(self, user_id: str) -> dict[str, Any]:
        """개인 소비 메모리 요약(묶음 · 최근 회고)을 조회한다."""

        return await self._request("GET", f"/internal/ai/users/{user_id}/memory")
