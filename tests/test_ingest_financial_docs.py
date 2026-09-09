"""적재 스크립트가 dry-run·빈 문서에서 DB를 건드리지 않고, 재적재 시 옛 Chunk를
source 단위로 정리하는지 확인한다.
"""

import asyncio
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.rag.embedding import FinancialEmbedder
from scripts.ingest_financial_docs import (
    _ID_MAX_LENGTH,
    _INGEST_EMBEDDING_TIMEOUT_SECONDS,
    _SOURCE_MAX_LENGTH,
    ingest,
    parse_args,
)


def _fail_if_called(*args: object, **kwargs: object) -> None:
    raise AssertionError("DATABASE_URL 없이는 asyncpg.connect가 호출되면 안 된다.")


def test_dry_run_skips_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("scripts.ingest_financial_docs.asyncpg.connect", _fail_if_called)
    document = tmp_path / "sample.txt"
    document.write_text("금융 문서 본문입니다. " * 200, encoding="utf-8")

    asyncio.run(ingest(document, source="sample.txt", dry_run=True))


def test_empty_document_skips_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("scripts.ingest_financial_docs.asyncpg.connect", _fail_if_called)
    document = tmp_path / "empty.txt"
    document.write_text("   ", encoding="utf-8")

    asyncio.run(ingest(document, source="empty.txt", dry_run=False))


def test_missing_database_url_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", "")
    get_settings.cache_clear()
    document = tmp_path / "sample.txt"
    document.write_text("금융 문서 본문입니다.", encoding="utf-8")

    with pytest.raises(SystemExit):
        asyncio.run(ingest(document, source="sample.txt", dry_run=False))

    get_settings.cache_clear()


class _FakeTransaction:
    async def __aenter__(self) -> "_FakeTransaction":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


class _FakeConnection:
    """`asyncpg.Connection`을 흉내 내 실행된 SQL과 인자를 기록한다."""

    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.closed = False

    def transaction(self) -> _FakeTransaction:
        return _FakeTransaction()

    async def execute(self, query: str, *args: object) -> None:
        self.executed.append((query, args))

    async def close(self) -> None:
        self.closed = True


def test_reingest_deletes_previous_chunks_by_source_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """문서가 줄어 Chunk 수가 바뀌어도, source 단위로 한 번만 지우고 다시 넣는다."""

    connection = _FakeConnection()

    async def fake_connect(_: str) -> _FakeConnection:
        return connection

    async def fake_embed(self: FinancialEmbedder, texts: list[str]) -> list[list[float]]:
        return [[0.0, 0.0] for _ in texts]

    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    get_settings.cache_clear()
    monkeypatch.setattr("scripts.ingest_financial_docs.asyncpg.connect", fake_connect)
    monkeypatch.setattr(FinancialEmbedder, "embed", fake_embed)

    document = tmp_path / "guide.txt"
    document.write_text("가나다라마바사아자차카타파하 " * 100, encoding="utf-8")

    asyncio.run(ingest(document, source="guide.txt", dry_run=False))

    delete_calls = [call for call in connection.executed if call[0].strip().startswith("DELETE")]
    insert_calls = [call for call in connection.executed if call[0].strip().startswith("INSERT")]

    assert len(delete_calls) == 1
    assert delete_calls[0][1] == ("guide.txt",)
    assert len(insert_calls) > 1  # 여러 Chunk가 생기는 긴 문서
    assert all(call[1][2] == "guide.txt" for call in insert_calls)  # source 컬럼
    assert connection.closed is True

    get_settings.cache_clear()


def test_ingest_uses_longer_embedding_timeout_than_realtime_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """대량 배치(최대 100 Chunk)를 보내는 이 스크립트는 FINANCE_QA 실시간 경로의
    `llm_timeout_seconds`(6초)가 아니라 별도의 더 긴 타임아웃을 써야 한다(PR #70 리뷰 5).
    """

    connection = _FakeConnection()
    recorded_kwargs: list[dict[str, object]] = []

    async def fake_connect(_: str) -> _FakeConnection:
        return connection

    class _FakeEmbedder:
        def __init__(self, **kwargs: object) -> None:
            recorded_kwargs.append(kwargs)

        async def embed(self, texts: list[str]) -> list[list[float]]:
            return [[0.0, 0.0] for _ in texts]

    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    get_settings.cache_clear()
    monkeypatch.setattr("scripts.ingest_financial_docs.asyncpg.connect", fake_connect)
    monkeypatch.setattr("scripts.ingest_financial_docs.FinancialEmbedder", _FakeEmbedder)

    document = tmp_path / "guide.txt"
    document.write_text("금융 문서 본문입니다.", encoding="utf-8")

    asyncio.run(ingest(document, source="guide.txt", dry_run=False))

    assert recorded_kwargs[0]["timeout_seconds"] == _INGEST_EMBEDDING_TIMEOUT_SECONDS

    get_settings.cache_clear()


def test_source_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """`--source`를 빠뜨리면 멈춘다 (PR #64 리뷰 2).

    기본값을 파일명으로 두면 빠뜨렸을 때 오류 없이 파일명으로 적재되고, 삭제 기준이
    `WHERE source = $1`이라 그 행은 이후 올바른 값으로 재적재해도 지워지지 않는다.
    """

    monkeypatch.setattr("sys.argv", ["ingest_financial_docs.py", "doc.txt"])

    with pytest.raises(SystemExit):
        parse_args()


@pytest.mark.parametrize("value", ["", " ", "\t\n"])
def test_blank_source_is_rejected(value: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """`--source ""`도 멈춘다 (PR #64 리뷰 2차).

    `required=True`는 옵션의 존재만 본다. 빈 `source`로 적재되면 다음 문서를 빈 값으로
    넣을 때 `DELETE ... WHERE source = ''`가 앞 문서를 통째로 지운다.
    """

    monkeypatch.setattr("sys.argv", ["ingest_financial_docs.py", "doc.txt", "--source", value])

    with pytest.raises(SystemExit):
        parse_args()


def test_too_long_source_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """`chunk_id`가 `VARCHAR(255)`를 넘길 식별자는 적재 전에 멈춘다 (PR #64 리뷰 3차).

    상한은 255가 아니라 `chunk_id = f"{source}-{index}"`의 접미사 자리를 뺀 값이다.
    255자 source는 첫 Chunk의 `chunk_id`부터 257자가 되어 INSERT에서 걸린다.
    """

    monkeypatch.setattr(
        "sys.argv",
        ["ingest_financial_docs.py", "doc.txt", "--source", "가" * (_SOURCE_MAX_LENGTH + 1)],
    )

    with pytest.raises(SystemExit):
        parse_args()

    monkeypatch.setattr(
        "sys.argv",
        ["ingest_financial_docs.py", "doc.txt", "--source", "가" * _SOURCE_MAX_LENGTH],
    )
    source = parse_args().source
    assert len(source) == _SOURCE_MAX_LENGTH
    # 통과한 경계값은 실제로 INSERT 가능해야 한다 — 마지막 Chunk까지 255자 안이다.
    assert len(f"{source}-9999999") <= _ID_MAX_LENGTH


def test_source_is_stripped(monkeypatch: pytest.MonkeyPatch) -> None:
    """앞뒤 공백은 떼고 쓴다 — 삭제 기준이 `WHERE source = $1`이라 공백 하나로 어긋난다."""

    monkeypatch.setattr(
        "sys.argv", ["ingest_financial_docs.py", "doc.txt", "--source", "  금융교과서-03-저축 "]
    )

    assert parse_args().source == "금융교과서-03-저축"
