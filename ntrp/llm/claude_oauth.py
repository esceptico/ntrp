import base64
import hashlib
import html
import json
import secrets
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Event

import httpx

from ntrp.config import load_user_settings, save_user_settings
from ntrp.logging import get_logger

_logger = get_logger(__name__)

CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
AUTH_URL = "https://claude.ai/oauth/authorize"
TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
SCOPES = "user:profile user:inference"

REFRESH_BUFFER = 300  # refresh 5min before expiry

CLAUDE_CREDENTIALS_PATH = Path.home() / ".claude" / ".credentials.json"
SETTINGS_KEY = "claude_oauth"
LOGIN_TIMEOUT = 120  # seconds to wait for OAuth callback

_cached_tokens: dict | None = None
_refresh_lock = threading.Lock()


def _generate_pkce() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


def _refresh_token(refresh_token: str) -> dict:
    data = {
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "refresh_token": refresh_token,
    }
    resp = httpx.post(TOKEN_URL, json=data)
    resp.raise_for_status()
    return resp.json()


def _store_tokens(token_data: dict) -> dict:
    global _cached_tokens
    expires_at = int(time.time()) + token_data.get("expires_in", 28800)
    oauth_data = {
        "access_token": token_data["access_token"],
        "refresh_token": token_data["refresh_token"],
        "expires_at": expires_at,
    }
    settings = load_user_settings()
    settings[SETTINGS_KEY] = oauth_data
    save_user_settings(settings)
    _cached_tokens = oauth_data
    return oauth_data


def _load_tokens() -> dict | None:
    global _cached_tokens
    if _cached_tokens:
        return _cached_tokens

    settings = load_user_settings()
    if data := settings.get(SETTINGS_KEY):
        _cached_tokens = data
        return data

    # Fallback: read from Claude Code credentials
    if CLAUDE_CREDENTIALS_PATH.exists():
        try:
            creds = json.loads(CLAUDE_CREDENTIALS_PATH.read_text())
            oauth = creds.get("claudeAiOauth", {})
            if oauth.get("accessToken") and oauth.get("refreshToken"):
                return {
                    "access_token": oauth["accessToken"],
                    "refresh_token": oauth["refreshToken"],
                    "expires_at": int(oauth.get("expiresAt", 0)) // 1000,
                }
        except (json.JSONDecodeError, OSError):
            pass

    return None


def login() -> dict:
    """Run the OAuth PKCE flow. Opens browser, waits for callback. Returns stored tokens."""
    verifier, challenge = _generate_pkce()
    state = secrets.token_hex(16)

    code_result: dict = {}
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
            pass  # suppress HTTP logs

    server = HTTPServer(("127.0.0.1", 0), CallbackHandler)
    port = server.server_address[1]
    redirect_uri = f"http://localhost:{port}/callback"

    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": SCOPES,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    _logger.info("Opening browser for Claude OAuth login (port %d)", port)
    webbrowser.open(auth_url)

    server.timeout = 5
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
    if code_result.get("state") != state:
        raise RuntimeError("OAuth state mismatch — possible CSRF attack")

    # Exchange code for tokens
    data = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "code": code_result["code"],
        "code_verifier": verifier,
        "redirect_uri": redirect_uri,
    }
    resp = httpx.post(TOKEN_URL, json=data)
    if resp.status_code != 200:
        _logger.error("Token exchange failed (%d): %s", resp.status_code, resp.text)
        try:
            body = resp.json()
            error = body.get("error", {})
            reason = error.get("message", str(error)) if isinstance(error, dict) else str(error)
        except Exception:
            reason = str(resp.status_code)
        raise RuntimeError(f"Token exchange failed: {reason}")
    token_data = resp.json()
    if "access_token" not in token_data or "refresh_token" not in token_data:
        raise RuntimeError("Token exchange failed: missing required fields")

    return _store_tokens(token_data)


def get_access_token() -> str | None:
    """Get a valid access token, refreshing if needed. Returns None if no OAuth configured."""
    tokens = _load_tokens()
    if not tokens:
        return None

    now = int(time.time())
    if now < tokens["expires_at"] - REFRESH_BUFFER:
        return tokens["access_token"]

    with _refresh_lock:
        # Re-check after acquiring lock (another thread may have refreshed)
        tokens = _load_tokens()
        if not tokens:
            return None
        if now < tokens["expires_at"] - REFRESH_BUFFER:
            return tokens["access_token"]

        _logger.info("Refreshing Claude OAuth token")
        try:
            token_data = _refresh_token(tokens["refresh_token"])
            stored = _store_tokens(token_data)
            return stored["access_token"]
        except (httpx.HTTPStatusError, KeyError, ValueError) as e:
            _logger.warning("OAuth token refresh failed: %s", e)
            return None


def is_configured() -> bool:
    return _load_tokens() is not None


def clear() -> None:
    global _cached_tokens
    _cached_tokens = None
    settings = load_user_settings()
    settings.pop(SETTINGS_KEY, None)
    save_user_settings(settings)
