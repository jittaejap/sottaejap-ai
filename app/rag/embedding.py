"""금융 문서 Embedding 생성 경계.

Provider와 모델을 아직 확정하지 않고 교체 가능한 비동기 인터페이스만 제공한다.
"""


class FinancialEmbedder:
    """Embedding Provider 연결을 위한 최소 클래스."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """텍스트 목록의 벡터를 반환한다."""

        # TODO: Embedding 모델과 차원 확정 후 실제 Provider를 연결한다.
        raise NotImplementedError("Embedding Provider가 아직 연결되지 않았습니다.")

