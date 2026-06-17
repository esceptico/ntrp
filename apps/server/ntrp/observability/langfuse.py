import os
import re
from contextlib import ExitStack, contextmanager, nullcontext
from typing import Any

from ntrp.logging import get_logger

_logger = get_logger(__name__)
_SECRET_KEY_PARTS = ("api_key", "apikey", "authorization", "cookie", "password", "secret", "token")
_BEARER_RE = re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+")
_SK_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b")
_MAX_TRACE_NAME_LENGTH = 200


def _env_enabled() -> bool:
    if os.getenv("LANGFUSE_TRACING_ENABLED", "").lower() == "false":
        return False
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


def _mask_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if any(part in str(key).lower() for part in _SECRET_KEY_PARTS) else _mask_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_mask_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_mask_value(item) for item in value)
    if isinstance(value, str):
        return _SK_RE.sub("[REDACTED]", _BEARER_RE.sub("Bearer [REDACTED]", value))
    return value


def _mask(*, data: Any, **_: Any) -> Any:
    return _mask_value(data)


def _trace_name(name: str) -> str:
    ascii_name = name.encode("ascii", "ignore").decode("ascii").strip()
    return (ascii_name or "ntrp.trace")[:_MAX_TRACE_NAME_LENGTH]


def _propagated_metadata(metadata: dict[str, Any] | None) -> dict[str, str] | None:
    if not metadata:
        return None
    return {key: str(value) for key, value in metadata.items() if value is not None}


class LangfuseTracer:
    def __init__(self) -> None:
        self._client = None
        self._loaded = False

    @property
    def enabled(self) -> bool:
        return _env_enabled() and self._client_or_none() is not None

    def _client_or_none(self):
        if not _env_enabled():
            return None
        if self._loaded:
            return self._client
        self._loaded = True
        try:
            from langfuse import Langfuse

            self._client = Langfuse(mask=_mask)
        except Exception as exc:
            _logger.warning("Langfuse tracing disabled: %s", exc)
            self._client = None
        return self._client

    @contextmanager
    def observation(self, *, name: str, as_type: str = "span", **kwargs: Any):
        client = self._client_or_none()
        if client is None:
            with nullcontext() as observation:
                yield observation
            return
        with ExitStack() as stack:
            try:
                observation = stack.enter_context(
                    client.start_as_current_observation(name=name, as_type=as_type, **kwargs)
                )
            except Exception as exc:
                _logger.warning("Langfuse observation failed: %s", exc)
                observation = None
            yield observation

    @contextmanager
    def trace(
        self,
        *,
        name: str,
        session_id: str | None = None,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        input: Any = None,
    ):
        client = self._client_or_none()
        if client is None:
            with nullcontext() as observation:
                yield observation
            return
        trace_name = _trace_name(name)
        with ExitStack() as stack:
            try:
                stack.enter_context(
                    client.propagate_attributes(
                        trace_name=trace_name,
                        session_id=session_id,
                        user_id=user_id,
                        metadata=_propagated_metadata(metadata),
                        tags=tags,
                    )
                )
                observation = stack.enter_context(
                    client.start_as_current_observation(
                        name=trace_name,
                        as_type="span",
                        input=input,
                        metadata=metadata,
                    )
                )
            except Exception as exc:
                _logger.warning("Langfuse trace failed: %s", exc)
                observation = None
            yield observation

    def flush(self) -> None:
        client = self._client_or_none()
        if client is None:
            return
        try:
            client.flush()
        except Exception as exc:
            _logger.warning("Langfuse flush failed: %s", exc)

    def shutdown(self) -> None:
        client = self._client_or_none()
        if client is None:
            return
        try:
            client.shutdown()
        except Exception as exc:
            _logger.warning("Langfuse shutdown failed: %s", exc)


_tracer = LangfuseTracer()


def get_langfuse_tracer() -> LangfuseTracer:
    return _tracer
