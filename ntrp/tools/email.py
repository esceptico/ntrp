from typing import Any

from pydantic import BaseModel, Field

from ntrp.constants import EMAIL_FROM_TRUNCATE, EMAIL_SUBJECT_TRUNCATE
from ntrp.sources.base import EmailSource
from ntrp.tools.core.base import ApprovalInfo, Tool, ToolResult
from ntrp.tools.core.context import ToolExecution
from ntrp.utils import truncate

SEND_EMAIL_DESCRIPTION = "Send an email from a specified Gmail account. Requires approval."

READ_EMAIL_DESCRIPTION = (
    "Read the full content of an email by its ID. Use emails() or emails(query) first to find email IDs."
)

EMAILS_DESCRIPTION = """Browse or search emails.

Without query: lists recent emails (subjects and senders). Use days to control time range.
With query: searches email content. Use specific keywords like names, subjects, or phrases.

Use read_email(id) to get full content of a specific email."""


class SendEmailInput(BaseModel):
    account: str = Field(description="Sender email address (must match a connected Gmail account)")
    to: str = Field(description="Recipient email address")
    subject: str = Field(description="Email subject")
    body: str = Field(description="Email body (plain text)")


class SendEmailTool(Tool):
    name = "send_email"
    description = SEND_EMAIL_DESCRIPTION
    mutates = True
    source_type = EmailSource
    input_model = SendEmailInput

    def __init__(self, source: EmailSource):
        self.source = source

    async def approval_info(self, account: str = "", to: str = "", subject: str = "", **kwargs: Any) -> ApprovalInfo | None:
        return ApprovalInfo(description=to, preview=f"Subject: {subject}\nFrom: {account}", diff=None)

    async def execute(
        self,
        execution: ToolExecution,
        account: str = "",
        to: str = "",
        subject: str = "",
        body: str = "",
        **kwargs: Any,
    ) -> ToolResult:
        if not account or not to:
            return ToolResult(content="Error: account and to are required", preview="Missing fields", is_error=True)

        result = self.source.send_email(account=account, to=to, subject=subject, body=body)
        return ToolResult(content=result, preview="Sent")


class ReadEmailInput(BaseModel):
    email_id: str = Field(description="The email ID (from search or list results)")


class ReadEmailTool(Tool):
    name = "read_email"
    description = READ_EMAIL_DESCRIPTION
    source_type = EmailSource
    input_model = ReadEmailInput

    def __init__(self, source: EmailSource):
        self.source = source

    async def execute(self, execution: ToolExecution, email_id: str = "", **kwargs: Any) -> ToolResult:
        if not email_id:
            return ToolResult(content="Error: email_id is required", preview="Missing email_id", is_error=True)

        content = self.source.read(email_id)
        if not content:
            return ToolResult(
                content=f"Email not found: {email_id}. Use emails() or emails(query) to find valid email IDs.",
                preview="Not found",
            )

        lines = content.count("\n") + 1
        return ToolResult(content=content, preview=f"Read {lines} lines")


def _format_email_list(emails: list) -> str:
    output = []
    for email in emails:
        title = truncate(email.title, EMAIL_SUBJECT_TRUNCATE) if email.title else "(no subject)"
        preview = truncate(email.preview, EMAIL_FROM_TRUNCATE) if email.preview else ""
        line = f"• {title}" + (f" ({preview})" if preview else "")
        if email.identity:
            line += f"  id: {email.identity}"
        output.append(line)
    return "\n".join(output)


def _format_email_search(results: list) -> str:
    output = []
    for item in results:
        meta = item.metadata
        subj = truncate(meta.get("subject", "No subject"), EMAIL_SUBJECT_TRUNCATE)
        frm = truncate(meta.get("from", ""), EMAIL_FROM_TRUNCATE)
        output.append(f"• {subj}")
        output.append(f"  from: {frm}, id: {item.source_id}")
    return "\n".join(output)


class EmailsInput(BaseModel):
    query: str | None = Field(default=None, description="Search query. Omit to list recent emails.")
    days: int = Field(default=7, description="How many days back to look when listing (default: 7)")
    limit: int = Field(default=30, description="Maximum results (default: 30)")


class EmailsTool(Tool):
    name = "emails"
    description = EMAILS_DESCRIPTION
    source_type = EmailSource
    input_model = EmailsInput

    def __init__(self, source: EmailSource):
        self.source = source

    async def execute(
        self, execution: ToolExecution, query: str | None = None, days: int = 7, limit: int = 30, **kwargs: Any
    ) -> ToolResult:
        if query:
            return self._search(query, limit)
        return self._list(days, limit)

    def _list(self, days: int, limit: int) -> ToolResult:
        accounts = self.source.list_accounts()
        emails = self.source.list_recent(days=days, limit=limit)

        if not emails:
            if accounts:
                return ToolResult(
                    content=f"No emails in last {days} days from {len(accounts)} accounts",
                    preview="0 emails",
                )
            return ToolResult(content=f"No emails in last {days} days", preview="0 emails")

        trimmed = emails[:limit]
        content = _format_email_list(trimmed)
        return ToolResult(content=content, preview=f"{len(emails)} emails")

    def _search(self, query: str, limit: int) -> ToolResult:
        results = self.source.search(query, limit=limit)
        if not results:
            return ToolResult(content=f"No emails found for '{query}'", preview="0 emails")

        trimmed = results[:limit]
        content = _format_email_search(trimmed)
        return ToolResult(content=content, preview=f"{len(results)} emails")
