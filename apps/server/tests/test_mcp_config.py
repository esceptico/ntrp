import pytest

from ntrp.mcp.models import HttpTransport, parse_server_config
from ntrp.tools.core.types import ToolAction, ToolScope


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


def test_parse_tool_policies():
    config = parse_server_config(
        "obsidian",
        {
            "transport": "http",
            "url": "127.0.0.1:8008/mcp",
            "tool_policies": {
                "search": {
                    "action": "read",
                    "scope": "external",
                    "requires_approval": False,
                    "permissions": ["mcp", "notes"],
                    "max_result_chars": 5000,
                }
            },
        },
    )

    policy = config.tool_policies["search"]
    assert policy.action is ToolAction.READ
    assert policy.scope is ToolScope.EXTERNAL
    assert policy.requires_approval is False
    assert policy.permissions == frozenset({"mcp", "notes"})
    assert policy.max_result_chars == 5000


def test_trust_tool_annotations_defaults_to_false():
    config = parse_server_config("obsidian", {"transport": "http", "url": "127.0.0.1:8008/mcp"})

    assert config.trust_tool_annotations is False
