from datetime import UTC, datetime
from typing import Any

import aiohttp

from ntrp.logging import get_logger
from ntrp.search.types import RawItem

_logger = get_logger(__name__)
_API = "https://slack.com/api"


def _ts_to_datetime(ts: str) -> datetime:
    try:
        return datetime.fromtimestamp(float(ts), tz=UTC)
    except (ValueError, TypeError):
        return datetime.now(UTC)


def _format_message(user_name: str, text: str, ts: str, channel_name: str | None = None) -> str:
    when = _ts_to_datetime(ts).isoformat()
    prefix = f"[{when}] {user_name}"
    if channel_name:
        prefix += f" in #{channel_name}"
    return f"{prefix}:\n{text}"


_USER_TOKEN_METHODS = frozenset({"assistant.search.context"})


class SlackClient:
    name = "slack"

    def __init__(self, bot_token: str | None = None, user_token: str | None = None):
        if not bot_token and not user_token:
            raise ValueError("SlackClient requires at least one of bot_token or user_token")
        self._bot_token = bot_token
        self._user_token = user_token
        # User token sees more (all the user's channels, search) — prefer it for reads.
        self._read_token = user_token or bot_token
        self._user_cache: dict[str, str] = {}
        self._channel_name_cache: dict[str, str] = {}
        self._channel_id_by_name: dict[str, str] = {}
        # DM channels: channel_id (D*) -> peer user_id; reverse by username + real_name.
        self._dm_peer_by_channel: dict[str, str] = {}
        self._dm_channel_by_user: dict[str, str] = {}
        # Whether we've refreshed the DM/MPIM index yet.
        self._dm_index_loaded = False

    def _token_for(self, method: str) -> str:
        if method in _USER_TOKEN_METHODS:
            if not self._user_token:
                raise RuntimeError(f"Slack {method} requires a user token (xoxp-) — set SLACK_USER_TOKEN")
            return self._user_token
        return self._read_token  # type: ignore[return-value]

    def _raise_for_error(self, method: str, data: dict, headers: dict) -> None:
        error = data.get("error", "unknown")
        # Slack returns `needed` (scope) and `provided` on missing_scope errors,
        # both in JSON body and X-OAuth-Scopes / X-Accepted-OAuth-Scopes headers.
        needed = data.get("needed") or headers.get("X-Accepted-OAuth-Scopes")
        provided = data.get("provided") or headers.get("X-OAuth-Scopes")
        token_kind = "user" if method in _USER_TOKEN_METHODS or self._token_for(method) is self._user_token else "bot"
        msg = f"Slack API {method} failed: {error}"
        if needed:
            msg += f" — needs scope: {needed}"
        if provided:
            msg += f" (have: {provided})"
        msg += f" [{token_kind} token]"
        raise RuntimeError(msg)

    async def _get(self, session: aiohttp.ClientSession, method: str, **params: Any) -> dict:
        headers = {"Authorization": f"Bearer {self._token_for(method)}"}
        async with session.get(f"{_API}/{method}", headers=headers, params=params) as resp:
            data = await resp.json()
            if not data.get("ok"):
                self._raise_for_error(method, data, dict(resp.headers))
            return data

    async def _post(self, session: aiohttp.ClientSession, method: str, **payload: Any) -> dict:
        headers = {
            "Authorization": f"Bearer {self._token_for(method)}",
            "Content-Type": "application/json; charset=utf-8",
        }
        async with session.post(f"{_API}/{method}", headers=headers, json=payload) as resp:
            data = await resp.json()
            if not data.get("ok"):
                self._raise_for_error(method, data, dict(resp.headers))
            return data

    async def _resolve_user(self, session: aiohttp.ClientSession, user_id: str) -> str:
        if not user_id:
            return "unknown"
        if user_id in self._user_cache:
            return self._user_cache[user_id]
        try:
            data = await self._get(session, "users.info", user=user_id)
            user = data["user"]
            name = user.get("real_name") or user.get("name") or user_id
        except Exception:
            name = user_id
        self._user_cache[user_id] = name
        return name

    async def _resolve_channel_id(self, session: aiohttp.ClientSession, channel: str) -> tuple[str, str]:
        """Return (channel_id, channel_name). Accepts id, '#name', or 'name'."""
        if channel.startswith("#"):
            channel = channel[1:]
        # Already a slack ID
        if channel and channel[0] in ("C", "G", "D") and channel.isalnum() and channel.isupper():
            cname = self._channel_name_cache.get(channel)
            if cname is None:
                try:
                    data = await self._get(session, "conversations.info", channel=channel)
                    cname = data["channel"].get("name", channel)
                except Exception:
                    cname = channel
                self._channel_name_cache[channel] = cname
            return channel, cname
        # Treat as name
        if cid := self._channel_id_by_name.get(channel):
            return cid, channel
        await self._refresh_channel_index(session)
        if cid := self._channel_id_by_name.get(channel):
            return cid, channel
        raise RuntimeError(f"Slack channel not found: {channel}")

    async def _refresh_channel_index(
        self,
        session: aiohttp.ClientSession,
        *,
        types: str = "public_channel,private_channel",
    ) -> None:
        cursor = ""
        while True:
            params: dict[str, Any] = {
                "limit": "1000",
                "exclude_archived": "true",
                "types": types,
            }
            if cursor:
                params["cursor"] = cursor
            data = await self._get(session, "conversations.list", **params)
            for ch in data.get("channels", []):
                cid = ch["id"]
                cname = ch.get("name", "")
                # Regular (public/private) channels have a name
                if cname:
                    self._channel_name_cache[cid] = cname
                    self._channel_id_by_name[cname] = cid
                # Direct messages (1-on-1): `is_im` + `user` field = peer user id
                if ch.get("is_im") and (peer := ch.get("user")):
                    self._dm_peer_by_channel[cid] = peer
                    self._dm_channel_by_user[peer] = cid
            cursor = data.get("response_metadata", {}).get("next_cursor", "")
            if not cursor:
                break
        if "im" in types:
            self._dm_index_loaded = True

    # -- public read methods --

    async def search_messages(
        self,
        query: str,
        limit: int = 20,
        *,
        channel_types: list[str] | None = None,
        include_context_messages: bool = False,
    ) -> list[RawItem]:
        """Search via the Real-time Search API (assistant.search.context).

        Requires user token with granular `search:read.*` scopes. The legacy
        `search.messages` method (which needed `search:read`) is deprecated.
        """
        async with aiohttp.ClientSession() as session:
            payload: dict[str, Any] = {
                "query": query,
                "limit": min(limit, 20),
                "content_types": ["messages"],
            }
            if channel_types:
                payload["channel_types"] = channel_types
            if include_context_messages:
                payload["include_context_messages"] = True
            data = await self._post(session, "assistant.search.context", **payload)
            messages = data.get("results", {}).get("messages", [])
            items: list[RawItem] = []
            for m in messages:
                cid = m.get("channel_id") or m.get("channel", {}).get("id", "")
                cname = m.get("channel_name") or m.get("channel", {}).get("name", "")
                ts = m.get("ts", "")
                user_id = m.get("user_id") or m.get("user", "")
                user_name = m.get("author_user_name") or await self._resolve_user(session, user_id)
                created = _ts_to_datetime(ts)
                items.append(
                    RawItem(
                        source=self.name,
                        source_id=f"{cid}:{ts}",
                        title=f"#{cname} — {user_name}",
                        content=m.get("content") or m.get("text", ""),
                        created_at=created,
                        updated_at=created,
                        metadata={
                            "channel_id": cid,
                            "channel_name": cname,
                            "user_id": user_id,
                            "user_name": user_name,
                            "ts": ts,
                            "permalink": m.get("permalink", ""),
                            "score": m.get("score"),
                        },
                    )
                )
            return items

    async def search_channels(self, query: str | None = None, limit: int = 50) -> list[dict[str, str]]:
        async with aiohttp.ClientSession() as session:
            await self._refresh_channel_index(session)
            results = []
            q = query.lower() if query else None
            for cid, cname in self._channel_name_cache.items():
                if q and q not in cname.lower():
                    continue
                results.append({"id": cid, "name": cname})
                if len(results) >= limit:
                    break
            return results

    async def list_dms(self, query: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """List open DMs (1-on-1) with resolved peer names.

        Requires `im:read` scope on the read token. Does NOT include group DMs (mpim).
        """
        async with aiohttp.ClientSession() as session:
            if not self._dm_index_loaded:
                await self._refresh_channel_index(session, types="im")
            results: list[dict[str, Any]] = []
            q = query.lower() if query else None
            for cid, peer_id in self._dm_peer_by_channel.items():
                peer_name = await self._resolve_user(session, peer_id)
                if q and q not in peer_name.lower() and q not in peer_id.lower():
                    continue
                results.append({"channel_id": cid, "user_id": peer_id, "peer": peer_name})
                if len(results) >= limit:
                    break
            return results

    async def open_dm(self, user_id: str) -> str:
        """Open (or fetch existing) DM channel with a user. Returns the DM channel id."""
        async with aiohttp.ClientSession() as session:
            # Check cache first to avoid an API call
            if cid := self._dm_channel_by_user.get(user_id):
                return cid
            data = await self._post(session, "conversations.open", users=user_id)
            cid = data.get("channel", {}).get("id", "")
            if cid:
                self._dm_peer_by_channel[cid] = user_id
                self._dm_channel_by_user[user_id] = cid
            return cid

    async def resolve_dm_target(self, target: str) -> str:
        """Resolve a DM target to a channel_id.

        Accepts:
          - DM channel id (D*)
          - user id (U*/W*)
          - @username or username (real_name or handle, case-insensitive)
        """
        # Already a DM channel id
        if target and target[0] == "D" and target.isalnum():
            return target
        # User id -> open DM
        stripped = target.lstrip("@")
        if stripped and stripped[0] in ("U", "W") and stripped.isalnum() and stripped.isupper():
            return await self.open_dm(stripped)
        # Name -> search users, then open DM with best match
        users = await self.search_users(stripped, limit=5)
        if not users:
            raise RuntimeError(f"No Slack user found matching {target!r}")
        user_id = users[0]["id"]
        return await self.open_dm(user_id)

    async def search_users(self, query: str | None = None, limit: int = 50) -> list[dict[str, str]]:
        async with aiohttp.ClientSession() as session:
            data = await self._get(session, "users.list", limit=str(limit))
            members = data.get("members", [])
            results = []
            q = query.lower() if query else None
            for m in members:
                if m.get("deleted") or m.get("is_bot"):
                    continue
                profile = m.get("profile", {})
                name = m.get("real_name") or m.get("name", "")
                email = profile.get("email", "")
                username = m.get("name", "")
                if q and q not in name.lower() and q not in email.lower() and q not in username.lower():
                    continue
                results.append(
                    {
                        "id": m.get("id", ""),
                        "name": name,
                        "username": username,
                        "email": email,
                        "title": profile.get("title", ""),
                    }
                )
                if len(results) >= limit:
                    break
            return results

    async def read_channel(self, channel: str, limit: int = 50) -> list[RawItem]:
        async with aiohttp.ClientSession() as session:
            cid, cname = await self._resolve_channel_id(session, channel)
            data = await self._get(session, "conversations.history", channel=cid, limit=str(limit))
            items: list[RawItem] = []
            for m in data.get("messages", []):
                ts = m.get("ts", "")
                user_id = m.get("user", "")
                user_name = await self._resolve_user(session, user_id) if user_id else (m.get("username") or "bot")
                created = _ts_to_datetime(ts)
                items.append(
                    RawItem(
                        source=self.name,
                        source_id=f"{cid}:{ts}",
                        title=f"#{cname} — {user_name}",
                        content=m.get("text", ""),
                        created_at=created,
                        updated_at=created,
                        metadata={
                            "channel_id": cid,
                            "channel_name": cname,
                            "user_id": user_id,
                            "user_name": user_name,
                            "ts": ts,
                            "thread_ts": m.get("thread_ts"),
                            "reply_count": m.get("reply_count", 0),
                        },
                    )
                )
            return items

    async def read_thread(self, source_id: str) -> str | None:
        """Read a message + thread replies. source_id is 'channel_id:ts'."""
        if ":" not in source_id:
            return None
        cid, ts = source_id.split(":", 1)
        async with aiohttp.ClientSession() as session:
            try:
                data = await self._get(session, "conversations.replies", channel=cid, ts=ts)
            except RuntimeError as e:
                _logger.warning("Slack read_thread failed: %s", e)
                return None
            messages = data.get("messages", [])
            if not messages:
                return None
            _, cname = await self._resolve_channel_id(session, cid)
            lines: list[str] = []
            for m in messages:
                user_id = m.get("user", "")
                user_name = await self._resolve_user(session, user_id) if user_id else (m.get("username") or "bot")
                lines.append(_format_message(user_name, m.get("text", ""), m.get("ts", ""), cname))
            return "\n\n".join(lines)

    async def read_user(self, user_id: str) -> dict[str, Any] | None:
        async with aiohttp.ClientSession() as session:
            try:
                data = await self._get(session, "users.info", user=user_id)
            except RuntimeError as e:
                _logger.warning("Slack read_user failed: %s", e)
                return None
            user = data.get("user")
            if not user:
                return None
            profile = user.get("profile", {})
            return {
                "id": user.get("id", ""),
                "name": user.get("real_name") or user.get("name", ""),
                "username": user.get("name", ""),
                "email": profile.get("email", ""),
                "title": profile.get("title", ""),
                "status_text": profile.get("status_text", ""),
                "status_emoji": profile.get("status_emoji", ""),
                "tz": user.get("tz", ""),
            }
