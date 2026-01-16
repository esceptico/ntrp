from typing import Any

from ntrp.constants import EMAIL_FROM_TRUNCATE, EMAIL_SUBJECT_TRUNCATE
from ntrp.sources.base import EmailSource
from ntrp.tools.core import Tool, ToolResult
from ntrp.tools.core.context import ToolExecution
from ntrp.utils import truncate


class SendEmailTool(Tool):
    name = "send_email"
    description = "Send an email from a specified Gmail account. Requires approval."
    mutates = True
    source_type = EmailSource

    def __init__(self, source: EmailSource):
        self.source = source

    @property
    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "account": {
                        "type": "string",
                        "description": "Sender email address (must match a connected Gmail account)",
                    },
                    "to": {"type": "string", "description": "Recipient email address"},
                    "subject": {"type": "string", "description": "Email subject"},
                    "body": {"type": "string", "description": "Email body (plain text)"},
                },
                "required": ["account", "to", "subject", "body"],
            },
        }

    async def execute(
        self,
        execution: ToolExecution,
        account: str = "",
        to: str = "",
        subject: str = "",
        body: str = "",
        **kwargs: Any,
    ) -> ToolResult:
        if not self.source:
            return ToolResult("Error: Gmail not available", "Not configured")
        if not account or not to:
            return ToolResult("Error: account and to are required", "Missing fields")

        await execution.require_approval(to, {"subject": subject, "from": account})

        result = self.source.send_email(account=account, to=to, subject=subject, body=body)
        return ToolResult(result, "Sent")


class ReadEmailTool(Tool):
    name = "read_email"
    description = "Read the full content of an email by its ID. Use search_email or list_email first to find email IDs."
    source_type = EmailSource

    def __init__(self, source: EmailSource):
        self.source = source

    @property
    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "email_id": {
                        "type": "string",
                        "description": "The email ID (from search or list results)",
                    },
                },
                "required": ["email_id"],
            },
        }

    async def execute(self, execution: ToolExecution, email_id: str = "", **kwargs: Any) -> ToolResult:
        if not email_id:
            return ToolResult("Error: email_id is required", "Missing email_id")

        content = self.source.read(email_id)
        if not content:
            return ToolResult(
                f"Email not found: {email_id}. Use search_email or list_email to find valid email IDs.",
                "Not found",
            )

        lines = content.count("\n") + 1
        return ToolResult(content, f"Read {lines} lines")


class ListEmailTool(Tool):
    name = "list_email"
    description = "List recent emails. Use read_email(id) to get full content."
    source_type = EmailSource

    def __init__(self, source: EmailSource):
        self.source = source

    @property
    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "How many days back to look (default: 7)"},
                    "limit": {"type": "integer", "description": "Maximum results (default: 30)"},
                },
                "required": [],
            },
        }

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
            output.append(f"• {title}" + (f" ({preview})" if preview else ""))

        return ToolResult("\n".join(output), f"{len(emails)} emails")


class SearchEmailTool(Tool):
    name = "search_email"
    description = "Search emails by content. Use read_email(id) to get full content."
    source_type = EmailSource

    def __init__(self, source: EmailSource):
        self.source = source

    @property
    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "description": "Maximum results (default: 10)"},
                },
                "required": ["query"],
            },
        }

    async def execute(self, execution: ToolExecution, query: str = "", limit: int = 10, **kwargs: Any) -> ToolResult:
        if not query:
            return ToolResult("Error: query is required", "Missing query")

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
