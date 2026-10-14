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


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"web_public_url": "https://front.example"}, "https://front.example"),
        (
            {"code_server_domain": "code.example", "web_port": 5174},
            "https://5174.code.example",
        ),
        ({"code_server_domain": "", "web_port": 5174}, "http://localhost:5174"),
    ],
)
def test_web_public_url_is_derived_when_unset(kwargs: dict, expected: str) -> None:
    base = {"web_public_url": "", "code_server_domain": "", "web_port": 5173}
    assert Settings(**{**base, **kwargs}).web_public_url == expected


def test_llm_request_timeout_defaults_to_120s_and_is_overridable(monkeypatch) -> None:
    assert Settings().llm_request_timeout == 120.0
    monkeypatch.setenv("LLM_REQUEST_TIMEOUT", "45")
    assert Settings().llm_request_timeout == 45.0


def test_llm_client_passes_the_timeout_to_chat_and_embeddings(monkeypatch) -> None:
    from app.core.config import get_settings
    from app.llm.client import LlmClient

    monkeypatch.setenv("LLM_REQUEST_TIMEOUT", "33")
    get_settings.cache_clear()
    try:
        client = LlmClient(base_url="http://llm.invalid/v1", api_key="k")
        assert client.chat_model("chat").request_timeout == 33.0
        assert client.embeddings("e").request_timeout == 33.0
    finally:
        get_settings.cache_clear()
