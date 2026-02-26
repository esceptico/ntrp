import asyncio
from typing import Any

from pydantic import BaseModel, Field

from ntrp.logging import get_logger
from ntrp.notifiers.base import Notifier
from ntrp.notifiers.log_store import NotificationLogStore
from ntrp.tools.core.base import Tool, ToolResult
from ntrp.tools.core.context import ToolExecution

NOTIFY_MAX_RETRIES = 3
NOTIFY_RETRY_DELAY = 2  # seconds

_logger = get_logger(__name__)

NOTIFY_DESCRIPTION = (
    "Send a notification to the user via their configured channels. "
    "Use this when the user asked to be notified, told, or written to about something."
)


class NotifyInput(BaseModel):
    subject: str = Field(description="Short notification subject/title")
    body: str = Field(description="Notification body — concise, informative")


class NotifyTool(Tool):
    name = "notify"
    display_name = "Notify"
    description = NOTIFY_DESCRIPTION
    mutates = True
    input_model = NotifyInput

    def __init__(
        self,
        notifiers: list[Notifier],
        log_store: NotificationLogStore,
        task_id: str,
    ):
        self._notifiers = notifiers
        self._log_store = log_store
        self._task_id = task_id

    async def execute(self, execution: ToolExecution, subject: str, body: str, **kwargs: Any) -> ToolResult:
        if not self._notifiers:
            return ToolResult(
                content="No notifiers configured for this task.",
                preview="No notifiers",
                is_error=True,
            )

        sent: list[str] = []
        failed: list[str] = []

        for notifier in self._notifiers:
            try:
                await self._send_with_retry(notifier, subject, body)
                sent.append(notifier.channel)
            except Exception:
                _logger.exception("Notifier %s failed after %d attempts", notifier.channel, NOTIFY_MAX_RETRIES)
                failed.append(notifier.channel)

        try:
            await self._log_store.save(self._task_id, subject, body, sent)
        except Exception:
            _logger.exception("Failed to log notification")

        if failed:
            return ToolResult(
                content=f"Sent to: {', '.join(sent)}. Failed: {', '.join(failed)}",
                preview=f"Partial ({len(sent)}/{len(sent) + len(failed)})",
            )

        return ToolResult(
            content=f"Notification sent to: {', '.join(sent)}",
            preview=f"Sent ({len(sent)})",
        )

    @staticmethod
    async def _send_with_retry(notifier: Notifier, subject: str, body: str) -> None:
        for attempt in range(NOTIFY_MAX_RETRIES):
            try:
                await notifier.send(subject, body)
                return
            except Exception:
                if attempt == NOTIFY_MAX_RETRIES - 1:
                    raise
                _logger.warning("Notifier %s attempt %d failed, retrying", notifier.channel, attempt + 1)
                await asyncio.sleep(NOTIFY_RETRY_DELAY * (attempt + 1))
