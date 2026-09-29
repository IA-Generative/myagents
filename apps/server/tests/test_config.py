import pytest

from app.core.config import Settings


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("postgresql://u:p@db:5432/x", "postgresql+asyncpg://u:p@db:5432/x"),
        ("postgres://u:p@db:5432/x", "postgresql+asyncpg://u:p@db:5432/x"),
        ("postgresql+asyncpg://u:p@db:5432/x", "postgresql+asyncpg://u:p@db:5432/x"),
        ("sqlite+aiosqlite:///./dev.db", "sqlite+aiosqlite:///./dev.db"),
    ],
)
def test_database_url_uses_async_driver(given: str, expected: str) -> None:
    assert Settings(database_url=given).database_url == expected
