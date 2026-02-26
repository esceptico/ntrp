import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

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
async def email_webhook(
    payload: EmailWebhookPayload,
    authorization: str | None = Header(default=None),
    webhook_token: str | None = Header(default=None, alias="X-Webhook-Token"),
):
    """Receive new-email notifications from an external webhook service."""
    runtime = get_runtime()
    expected_token = runtime.config.webhook_token or runtime.config.api_key
    if expected_token:
        has_valid_header = bool(webhook_token) and secrets.compare_digest(webhook_token, expected_token)
        has_valid_bearer = authorization == f"Bearer {expected_token}"
        if not has_valid_header and not has_valid_bearer:
            raise HTTPException(status_code=401, detail="Unauthorized webhook request")

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

    runtime.channel.publish(event)
    _logger.info("Email webhook: published NewEmail %s", event.email_id)

    return {"status": "ok"}
