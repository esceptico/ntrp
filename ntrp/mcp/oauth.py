import asyncio
import html
import json
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Event
from typing import Any

from mcp.client.auth import OAuthClientProvider
from mcp.client.streamable_http import create_mcp_http_client
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

from ntrp.logging import get_logger

_logger = get_logger(__name__)

OAUTH_DIR = Path.home() / ".ntrp" / "mcp_oauth"
LOGIN_TIMEOUT = 120


class MCPTokenStorage:
    def __init__(self, server_name: str):
        self._path = OAUTH_DIR / f"{server_name}.json"

    def _read(self) -> dict:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _write(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2))

    async def get_tokens(self) -> OAuthToken | None:
        data = self._read()
        if tokens := data.get("tokens"):
            return OAuthToken(**tokens)
        return None

    async def set_tokens(self, tokens: OAuthToken) -> None:
        data = self._read()
        data["tokens"] = tokens.model_dump(exclude_none=True)
        self._write(data)

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        data = self._read()
        if client := data.get("client_info"):
            return OAuthClientInformationFull(**client)
        return None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        data = self._read()
        data["client_info"] = client_info.model_dump(exclude_none=True)
        self._write(data)


def create_oauth_provider(server_name: str, server_url: str) -> OAuthClientProvider:
    return OAuthClientProvider(
        server_url=server_url,
        client_metadata=OAuthClientMetadata(
            redirect_uris=["http://localhost:0/callback"],
            client_name="NTRP",
        ),
        storage=MCPTokenStorage(server_name),
        redirect_handler=None,
        callback_handler=None,
    )


def run_mcp_oauth(server_name: str, server_url: str) -> None:
    code_result: dict[str, Any] = {}
    done = Event()

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return

            params = urllib.parse.parse_qs(parsed.query)
            if "code" in params:
                code_result["code"] = params["code"][0]
                code_result["state"] = params.get("state", [None])[0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<html><body><h2>Connected! You can close this tab.</h2></body></html>")
            else:
                error = params.get("error", ["unknown"])[0]
                code_result["error"] = error
                self.send_response(400)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(f"<html><body><h2>Error: {html.escape(error)}</h2></body></html>".encode())
            done.set()

        def log_message(self, format, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), CallbackHandler)
    port = server.server_address[1]
    redirect_uri = f"http://localhost:{port}/callback"

    async def redirect_handler(url: str) -> None:
        _logger.info("Opening browser for MCP OAuth (server=%r, port=%d)", server_name, port)
        webbrowser.open(url)

    async def callback_handler() -> tuple[str, str | None]:
        server.timeout = 5
        import time

        deadline = time.time() + LOGIN_TIMEOUT
        while not done.is_set():
            if time.time() > deadline:
                server.server_close()
                raise RuntimeError("OAuth timed out — no callback received within 120s")
            server.handle_request()
        server.server_close()

        if "error" in code_result:
            raise RuntimeError(f"OAuth failed: {code_result['error']}")
        if "code" not in code_result:
            raise RuntimeError("OAuth timed out — no authorization code received")
        return (code_result["code"], code_result.get("state"))

    storage = MCPTokenStorage(server_name)

    provider = OAuthClientProvider(
        server_url=server_url,
        client_metadata=OAuthClientMetadata(
            redirect_uris=[redirect_uri],
            client_name="NTRP",
        ),
        storage=storage,
        redirect_handler=redirect_handler,
        callback_handler=callback_handler,
        timeout=LOGIN_TIMEOUT,
    )

    loop = asyncio.new_event_loop()
    try:

        async def _run():
            async with create_mcp_http_client(auth=provider) as client:
                # Make a request to the server URL to trigger the OAuth flow.
                # The OAuthClientProvider intercepts the 401 and runs auth.
                resp = await client.get(server_url)
                _logger.info("MCP OAuth completed for %r (status=%d)", server_name, resp.status_code)

        loop.run_until_complete(_run())
    finally:
        loop.close()


def clear_tokens(server_name: str) -> None:
    path = OAUTH_DIR / f"{server_name}.json"
    if path.exists():
        path.unlink()
