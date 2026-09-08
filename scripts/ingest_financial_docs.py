"""금융 문서 적재 파이프라인의 로컬 진입점.

텍스트 → Chunk → Embedding → `financial_chunks` 저장까지 실행한다.

`financial_chunks` 테이블은 `sottaejap-server`의 Flyway(V8)가 소유한다 (04 §1).
여기서는 테이블·확장을 만들지 않고 이미 있는 테이블에 쓰기만 한다. `chunk_id`에는
UNIQUE 제약이 있고(V8), 재적재 전제는 `ON CONFLICT (chunk_id) DO UPDATE`다 (01 E-85).
문서 본문이 줄어 Chunk 개수가 줄면 뒤쪽 옛 Chunk가 `ON CONFLICT`만으로는 안 지워지므로,
같은 `source`의 기존 행을 먼저 전부 지우고 다시 넣는다 — 한 트랜잭션으로 묶어 중간에
실패해도 새 내용과 옛 내용이 섞여 남지 않게 한다.

`source`는 문서의 식별자다 — 재적재 삭제 기준이 `source` 컬럼이라, 같은 문서를 다른
`--source` 값으로 다시 넣으면 새 값으로 저장되고 이전 값의 행은 지워지지 않은 채 남는다.
한 번 정한 `source`는 그 문서에 계속 같은 값으로 쓴다. `chunk_id`·`source`는 V8에서
`VARCHAR(255)`라 짧은 식별자를 쓴다.
"""

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import asyncpg  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.rag.chunker import chunk_text  # noqa: E402
from app.rag.embedding import FinancialEmbedder  # noqa: E402
from app.rag.retriever import to_vector_literal  # noqa: E402

_DELETE_BY_SOURCE_SQL = "DELETE FROM financial_chunks WHERE source = $1"
_UPSERT_SQL = """
INSERT INTO financial_chunks (chunk_id, content, source, metadata, embedding)
VALUES ($1, $2, $3, $4::jsonb, $5::vector)
ON CONFLICT (chunk_id) DO UPDATE SET
    content = EXCLUDED.content,
    source = EXCLUDED.source,
    metadata = EXCLUDED.metadata,
    embedding = EXCLUDED.embedding
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="금융 문서를 Chunk·Embedding해 financial_chunks에 적재한다"
    )
    parser.add_argument("document", type=Path, help="UTF-8 텍스트 문서 경로")
    parser.add_argument(
        "--source",
        help="문서 식별자 (기본: 파일명). 한 번 정하면 바꾸지 않는다 — 짧게",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chunk 개수만 확인하고 Embedding·DB 적재는 건너뛴다",
    )
    return parser.parse_args()


async def ingest(document: Path, source: str, dry_run: bool) -> None:
    """문서 하나를 Chunk로 나누고, `dry_run`이 아니면 Embedding해 저장한다."""

    text = document.read_text(encoding="utf-8")
    chunks = chunk_text(text)
    print(f"{len(chunks)}개 Chunk를 생성했습니다.")

    if dry_run or not chunks:
        return

    settings = get_settings()
    if not settings.database_url:
        raise SystemExit("DATABASE_URL이 설정되지 않았습니다.")

    embedder = FinancialEmbedder(settings=settings)
    vectors = await embedder.embed(chunks)

    # 일회성 스크립트라 풀이 아니라 연결 하나면 충분하다.
    conn = await asyncpg.connect(settings.database_url)
    try:
        async with conn.transaction():
            # 같은 source의 옛 Chunk를 전부 지운 뒤 다시 넣는다 — 문서가 줄어
            # Chunk 개수가 준 경우에도 뒤쪽 옛 Chunk가 남지 않는다.
            await conn.execute(_DELETE_BY_SOURCE_SQL, source)
            for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
                chunk_id = f"{source}-{index}"
                await conn.execute(
                    _UPSERT_SQL,
                    chunk_id,
                    chunk,
                    source,
                    "{}",
                    to_vector_literal(vector),
                )
        print(f"{len(chunks)}개 Chunk를 저장했습니다.")
    finally:
        await conn.close()


def main() -> None:
    args = parse_args()
    source = args.source or args.document.name
    asyncio.run(ingest(args.document, source, args.dry_run))


if __name__ == "__main__":
    main()
