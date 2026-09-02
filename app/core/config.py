"""환경 변수 기반 애플리케이션 설정.

설정값만 관리하며 외부 연결을 직접 만들거나 서비스 정책을 결정하지 않는다.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """소때잡 AI 서버 실행 설정 (07 §3)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str | None = Field(default=None, repr=False)
    openai_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 8.0
    spring_base_url: str = "http://localhost:8080"
    spring_timeout_seconds: float = 10.0
    internal_shared_secret: str | None = Field(default=None, repr=False)
    database_url: str | None = Field(default=None, repr=False)
    ai_server_host: str = "0.0.0.0"
    ai_server_port: int = 8000


@lru_cache
def get_settings() -> Settings:
    """프로세스에서 재사용할 설정 인스턴스를 반환한다."""

    return Settings()
