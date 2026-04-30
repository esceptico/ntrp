import pytest

from ntrp.mcp.models import HttpTransport, parse_server_config


def test_http_url_without_scheme_defaults_to_http():
    config = parse_server_config("obsidian", {"transport": "http", "url": "localhost:8008/mcp"})

    assert isinstance(config.transport, HttpTransport)
    assert config.transport.url == "http://localhost:8008/mcp"


def test_http_url_preserves_authorization_headers():
    config = parse_server_config(
        "obsidian",
        {
            "transport": "http",
            "url": "127.0.0.1:8008/mcp",
            "headers": {"Authorization": "Bearer <token>"},
        },
    )

    assert isinstance(config.transport, HttpTransport)
    assert config.transport.headers == {"Authorization": "Bearer <token>"}


def test_http_url_rejects_non_http_scheme():
    with pytest.raises(ValueError, match="http url must use http:// or https://"):
        parse_server_config("obsidian", {"transport": "http", "url": "ftp://localhost:8008/mcp"})


def test_http_url_rejects_missing_host():
    with pytest.raises(ValueError, match="http url must use http:// or https://"):
        parse_server_config("obsidian", {"transport": "http", "url": "http:///mcp"})
