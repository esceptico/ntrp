from dataclasses import dataclass, field


@dataclass(frozen=True)
class StdioTransport:
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] | None = None


@dataclass(frozen=True)
class HttpTransport:
    url: str


@dataclass(frozen=True)
class MCPServerConfig:
    name: str
    transport: StdioTransport | HttpTransport


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
        transport = HttpTransport(url=url)
    else:
        raise ValueError(f"MCP server {name!r}: unknown transport {transport_type!r} (expected 'stdio' or 'http')")
    return MCPServerConfig(name=name, transport=transport)
