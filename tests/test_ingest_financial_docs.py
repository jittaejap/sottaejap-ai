"""적재 스크립트가 dry-run과 빈 문서에서 DB를 건드리지 않는지 확인한다."""

import asyncio
from pathlib import Path

import pytest

from scripts.ingest_financial_docs import ingest


def _fail_if_called(*args: object, **kwargs: object) -> None:
    raise AssertionError("DATABASE_URL 없이는 asyncpg.create_pool이 호출되면 안 된다.")


def test_dry_run_skips_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("scripts.ingest_financial_docs.asyncpg.create_pool", _fail_if_called)
    document = tmp_path / "sample.txt"
    document.write_text("금융 문서 본문입니다. " * 200, encoding="utf-8")

    asyncio.run(ingest(document, source="sample.txt", dry_run=True))


def test_empty_document_skips_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("scripts.ingest_financial_docs.asyncpg.create_pool", _fail_if_called)
    document = tmp_path / "empty.txt"
    document.write_text("   ", encoding="utf-8")

    asyncio.run(ingest(document, source="empty.txt", dry_run=False))


def test_missing_database_url_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", "")
    from app.core.config import get_settings

    get_settings.cache_clear()
    document = tmp_path / "sample.txt"
    document.write_text("금융 문서 본문입니다.", encoding="utf-8")

    with pytest.raises(SystemExit):
        asyncio.run(ingest(document, source="sample.txt", dry_run=False))

    get_settings.cache_clear()
