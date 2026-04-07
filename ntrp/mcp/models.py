from dataclasses import dataclass, field


@dataclass(frozen=True)
class StdioTransport:
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] | None = None


@dataclass(frozen=True)
class HttpTransport:
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    auth: str | None = None
    client_id: str | None = None
    client_secret: str | None = None


@dataclass(frozen=True)
class MCPServerConfig:
    name: str
    transport: StdioTransport | HttpTransport
    tools: list[str] | None = None


def parse_server_config(name: str, raw: dict) -> MCPServerConfig:
    transport_type = raw.get("transport")
    if transport_type == "stdio":
        command = raw.get("command")
        if not command:
            raise ValueError(f"MCP server {name!r}: stdio transport requires 'command'")
        transport = StdioTransport(
            command=command,
            args=raw.get("args", []),
            env=raw.get("env"),
        )
    elif transport_type == "http":
        url = raw.get("url")
        if not url:
            raise ValueError(f"MCP server {name!r}: http transport requires 'url'")
        transport = HttpTransport(
            url=url,
            headers=raw.get("headers", {}),
            auth=raw.get("auth"),
            client_id=raw.get("client_id"),
            client_secret=raw.get("client_secret"),
        )
    else:
        raise ValueError(f"MCP server {name!r}: unknown transport {transport_type!r} (expected 'stdio' or 'http')")
    tools = raw.get("tools")
    return MCPServerConfig(name=name, transport=transport, tools=tools)
