from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ntrp.events.triggers import NewEmail
from ntrp.logging import get_logger
from ntrp.server.runtime import get_runtime

_logger = get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class EmailWebhookPayload(BaseModel):
    email_id: str
    subject: str = "(no subject)"
    sender: str = "unknown"
    snippet: str = ""
    received_at: datetime | None = None


@router.post("/email")
async def email_webhook(payload: EmailWebhookPayload):
    """Receive new-email notifications from an external webhook service."""
    received = payload.received_at or datetime.now(UTC)
    if received.tzinfo is None:
        received = received.replace(tzinfo=UTC)

    event = NewEmail(
        email_id=payload.email_id,
        subject=payload.subject,
        sender=payload.sender,
        snippet=payload.snippet,
        received_at=received,
    )

    runtime = get_runtime()
    runtime.channel.publish(event)
    _logger.info("Email webhook: published NewEmail %s", event.email_id)

    return {"status": "ok"}
