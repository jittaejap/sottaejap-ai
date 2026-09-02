"""Spring 서비스 API 호출을 전담하는 HTTP Client.

Tool은 이 Client의 도메인 메서드만 사용한다. 아직 Spring Endpoint 명세가 없으므로
경로를 임의로 만들지 않고 각 메서드는 명시적인 미설정 오류를 반환한다.
"""

from typing import Any, NoReturn

import httpx

from app.core.config import Settings, get_settings


class SpringEndpointNotConfiguredError(RuntimeError):
    """Spring API 경로/응답 명세가 아직 확정되지 않은 경우."""


class SpringClient:
    """Spring Boot HTTP API에 접근하는 유일한 Client."""

    def __init__(
        self,
        settings: Settings | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._owns_client = http_client is None
        self._http = http_client or httpx.AsyncClient(
            base_url=self._settings.spring_base_url,
            timeout=self._settings.spring_timeout_seconds,
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
        """확정된 Endpoint를 호출하고 JSON 객체를 반환한다."""

        response = await self._http.request(method, endpoint, **kwargs)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Spring API 응답은 JSON object여야 합니다.")
        return payload

    async def get_transactions(
        self, user_id: str, query: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """거래 조회 API를 호출한다."""

        self._not_configured("거래 조회")

    async def get_reflections(self, user_id: str) -> dict[str, Any]:
        """회고 조회 API를 호출한다."""

        self._not_configured("회고 조회")

    async def save_reflection(
        self, user_id: str, reflection: dict[str, Any]
    ) -> dict[str, Any]:
        """검증된 회고 저장 API를 호출한다."""

        self._not_configured("회고 저장")

    async def get_behavior_analysis(self, user_id: str) -> dict[str, Any]:
        """Spring Rule Engine의 소비 분석 결과를 조회한다."""

        self._not_configured("소비 분석")

    async def get_action_plan(self, user_id: str) -> dict[str, Any]:
        """Spring이 계산한 행동 조정 및 예상 절감 결과를 조회한다."""

        self._not_configured("행동 제안")

    async def get_memory(self, user_id: str) -> dict[str, Any]:
        """현재 저장 구현과 무관하게 개인 소비 메모리를 조회한다."""

        self._not_configured("개인 소비 메모리")

    @staticmethod
    def _not_configured(operation: str) -> NoReturn:
        # TODO: Spring API 명세 확정 후 실제 경로, 요청, 응답 DTO를 연결한다.
        raise SpringEndpointNotConfiguredError(
            f"{operation} Spring API Endpoint가 아직 확정되지 않았습니다."
        )

