from typing import Any

from pydantic import BaseModel, Field

from ntrp.constants import EMAIL_FROM_TRUNCATE, EMAIL_SUBJECT_TRUNCATE
from ntrp.sources.base import EmailSource
from ntrp.tools.core.base import Tool, ToolResult
from ntrp.tools.core.context import ToolExecution
from ntrp.utils import truncate

SEND_EMAIL_DESCRIPTION = "Send an email from a specified Gmail account. Requires approval."

READ_EMAIL_DESCRIPTION = (
    "Read the full content of an email by its ID. Use search_email or list_email first to find email IDs."
)

LIST_EMAIL_DESCRIPTION = (
    "List recent emails (subjects only). Use search_email() to find email IDs, then read_email(id) for full content."
)

SEARCH_EMAIL_DESCRIPTION = "Search emails by content. Use read_email(id) to get full content."


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
            return ToolResult("Error: account and to are required", "Missing fields", is_error=True)

        await execution.require_approval(to, preview=f"Subject: {subject}\nFrom: {account}")

        result = self.source.send_email(account=account, to=to, subject=subject, body=body)
        return ToolResult(result, "Sent")


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
            return ToolResult("Error: email_id is required", "Missing email_id", is_error=True)

        content = self.source.read(email_id)
        if not content:
            return ToolResult(
                f"Email not found: {email_id}. Use search_email or list_email to find valid email IDs.",
                "Not found",
            )

        lines = content.count("\n") + 1
        return ToolResult(content, f"Read {lines} lines")


class ListEmailInput(BaseModel):
    days: int = Field(default=7, description="How many days back to look (default: 7)")
    limit: int = Field(default=30, description="Maximum results (default: 30)")


class ListEmailTool(Tool):
    name = "list_email"
    description = LIST_EMAIL_DESCRIPTION
    source_type = EmailSource
    input_model = ListEmailInput

    def __init__(self, source: EmailSource):
        self.source = source

    async def execute(self, execution: ToolExecution, days: int = 7, limit: int = 30, **kwargs: Any) -> ToolResult:
        accounts = self.source.list_accounts()
        emails = self.source.list_recent(days=days, limit=limit)

        if not emails:
            if accounts:
                return ToolResult(f"No emails in last {days} days from {len(accounts)} accounts", "0 emails")
            return ToolResult(f"No emails in last {days} days", "0 emails")

        output = []
        for email in emails[:limit]:
            title = truncate(email.title, EMAIL_SUBJECT_TRUNCATE) if email.title else "(no subject)"
            preview = truncate(email.preview, EMAIL_FROM_TRUNCATE) if email.preview else ""
            line = f"• {title}" + (f" ({preview})" if preview else "")
            if email.identity:
                line += f"  id: {email.identity}"
            output.append(line)

        return ToolResult("\n".join(output), f"{len(emails)} emails")


class SearchEmailInput(BaseModel):
    query: str = Field(description="Search query")
    limit: int = Field(default=10, description="Maximum results (default: 10)")


class SearchEmailTool(Tool):
    name = "search_email"
    description = SEARCH_EMAIL_DESCRIPTION
    source_type = EmailSource
    input_model = SearchEmailInput

    def __init__(self, source: EmailSource):
        self.source = source

    async def execute(self, execution: ToolExecution, query: str = "", limit: int = 10, **kwargs: Any) -> ToolResult:
        if not query:
            return ToolResult("Error: query is required", "Missing query", is_error=True)

        results = self.source.search(query, limit=limit)
        if not results:
            return ToolResult(f"No emails found for '{query}'", "0 emails")

        output = []
        for item in results[:limit]:
            meta = item.metadata
            subj = truncate(meta.get("subject", "No subject"), EMAIL_SUBJECT_TRUNCATE)
            frm = truncate(meta.get("from", ""), EMAIL_FROM_TRUNCATE)
            output.append(f"• {subj}")
            output.append(f"  from: {frm}, id: {item.source_id}")

        return ToolResult("\n".join(output), f"{len(results)} emails")
