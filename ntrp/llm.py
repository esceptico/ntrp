"""LLM completion wrappers with retry and exponential backoff."""

import asyncio
import logging
import random

import litellm

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
BASE_DELAY = 0.5
MAX_DELAY = 8.0
JITTER = 0.25

_RETRYABLE_STATUS_CODES = {408, 409, 429}
_RETRYABLE_ERROR_NAMES = {"ECONNRESET", "ETIMEDOUT"}


def _is_retryable(exc: Exception) -> tuple[bool, float | None]:
    """Check if an exception is retryable. Returns (retryable, retry_after)."""
    status = getattr(exc, "status_code", None)

    if status is not None:
        if status in _RETRYABLE_STATUS_CODES or status >= 500:
            # Check for retry-after header
            headers = getattr(exc, "headers", None) or {}
            retry_after = None
            if raw := headers.get("retry-after"):
                try:
                    retry_after = float(raw)
                except (ValueError, TypeError):
                    pass
            return True, retry_after

    err_name = type(exc).__name__
    if any(name in err_name for name in _RETRYABLE_ERROR_NAMES):
        return True, None

    msg = str(exc).lower()
    if "overloaded" in msg or "rate_limit" in msg or "timeout" in msg:
        return True, None

    return False, None


def _delay(attempt: int, retry_after: float | None) -> float:
    if retry_after is not None:
        return min(retry_after, MAX_DELAY)
    base = min(BASE_DELAY * (2 ** attempt), MAX_DELAY)
    jitter = base * JITTER * (2 * random.random() - 1)
    return base + jitter


async def acompletion(**kwargs):
    """litellm.acompletion with retry + exponential backoff."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            return await litellm.acompletion(**kwargs)
        except Exception as e:
            retryable, retry_after = _is_retryable(e)
            if not retryable or attempt >= MAX_RETRIES:
                raise
            wait = _delay(attempt, retry_after)
            logger.warning("LLM call failed (attempt %d/%d), retrying in %.1fs: %s", attempt + 1, MAX_RETRIES, wait, e)
            await asyncio.sleep(wait)


def completion(**kwargs):
    """litellm.completion with retry + exponential backoff (sync)."""
    import time

    for attempt in range(MAX_RETRIES + 1):
        try:
            return litellm.completion(**kwargs)
        except Exception as e:
            retryable, retry_after = _is_retryable(e)
            if not retryable or attempt >= MAX_RETRIES:
                raise
            wait = _delay(attempt, retry_after)
            logger.warning("LLM call failed (attempt %d/%d), retrying in %.1fs: %s", attempt + 1, MAX_RETRIES, wait, e)
            time.sleep(wait)
