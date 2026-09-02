"""금융 텍스트를 단순한 중첩 Chunk로 나눈다.

MVP용 결정적 분할만 제공하며 문서 저장이나 Embedding은 수행하지 않는다.
"""


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """문자 수 기준으로 텍스트를 분할한다."""

    if chunk_size <= 0:
        raise ValueError("chunk_size는 1 이상이어야 합니다.")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap은 0 이상 chunk_size 미만이어야 합니다.")

    normalized = text.strip()
    if not normalized:
        return []

    step = chunk_size - overlap
    return [normalized[start : start + chunk_size] for start in range(0, len(normalized), step)]

