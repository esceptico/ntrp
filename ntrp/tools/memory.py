from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from ntrp.memory.formatting import format_memory_context
from ntrp.tools.core.base import ApprovalInfo, Tool, ToolResult
from ntrp.tools.core.context import ToolExecution

RECALL_DESCRIPTION = """Recall stored facts from memory about a topic or entity.

WHEN TO USE:
- Before answering questions about the user, their preferences, people they know, or past conversations
- When the user references something you should know ("remember when...", "what did I say about...")
- Before asking the user something they may have already told you
- When a topic comes up that might have stored context (projects, people, plans, opinions)

Your system prompt has a small memory snapshot — recall() searches the FULL memory store which is much richer.

PREFER recall() FOR: Known facts, user preferences, stored knowledge, past context
PREFER search() FOR: Finding new info in notes/emails/web pages"""

FORGET_DESCRIPTION = "Delete facts from memory by semantic search."

REMEMBER_DESCRIPTION = """Store a fact in memory for future recall.

WHEN TO USE:
- After learning something important about the user
- After discovering a key fact from notes/emails
- To record user preferences or decisions

IMPORTANT: Only store facts that would be useful to recall in 6+ months.
BAD: "Python is a programming language" (not user-specific)"""


class RememberInput(BaseModel):
    fact: str = Field(description="The fact to remember (natural language).")
    source: str | None = Field(default=None, description="Where this fact came from (e.g. file path, email id).")
    happened_at: str | None = Field(
        default=None, description="ISO timestamp of when the event occurred (for temporal linking)."
    )


class RememberTool(Tool):
    name = "remember"
    display_name = "Remember"
    description = REMEMBER_DESCRIPTION
    mutates = True
    requires = frozenset({"memory"})
    input_model = RememberInput

    async def approval_info(self, execution: ToolExecution, fact: str, **kwargs: Any) -> ApprovalInfo | None:
        return ApprovalInfo(description=fact[:100], preview=None, diff=None)

    async def execute(
        self,
        execution: ToolExecution,
        fact: str,
        source: str | None = None,
        happened_at: str | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        memory = execution.ctx.services["memory"]
        event_time = datetime.fromisoformat(happened_at) if happened_at else None

        result = await memory.remember(
            text=fact,
            source_type="chat",
            source_ref=source,
            happened_at=event_time,
        )

        if not result:
            return ToolResult(content="Already known — reinforced existing memory.", preview="Already known")

        entities = ", ".join(result.entities_extracted) if result.entities_extracted else "none"
        return ToolResult(
            content=f"Remembered: {result.fact.text}\nEntities: {entities}",
            preview="Remembered",
        )


_DEFAULT_RECALL_LIMIT = 5


class RecallInput(BaseModel):
    query: str = Field(description="What to recall.")
    limit: int = Field(
        default=_DEFAULT_RECALL_LIMIT, description=f"Number of seed facts (default {_DEFAULT_RECALL_LIMIT})."
    )


class RecallTool(Tool):
    name = "recall"
    display_name = "Recall"
    description = RECALL_DESCRIPTION
    requires = frozenset({"memory"})
    input_model = RecallInput

    async def execute(
        self, execution: ToolExecution, query: str, limit: int = _DEFAULT_RECALL_LIMIT, **kwargs: Any
    ) -> ToolResult:
        memory = execution.ctx.services["memory"]
        context = await memory.recall(query=query, limit=limit)
        formatted = format_memory_context(
            query_facts=context.facts,
            query_observations=context.observations,
            bundled_sources=context.bundled_sources,
        )
        if formatted:
            obs_count = len(context.observations)
            fact_count = len(context.facts)
            return ToolResult(content=formatted, preview=f"{obs_count} patterns, {fact_count} facts")
        return ToolResult(
            content="No memory found for this query. Try broader terms or use remember() to store facts first.",
            preview="0 facts",
        )


class ForgetInput(BaseModel):
    query: str = Field(description="Description of facts to forget.")


class ForgetTool(Tool):
    name = "forget"
    display_name = "Forget"
    description = FORGET_DESCRIPTION
    mutates = True
    requires = frozenset({"memory"})
    input_model = ForgetInput

    async def approval_info(self, execution: ToolExecution, query: str, **kwargs: Any) -> ApprovalInfo | None:
        return ApprovalInfo(description=query, preview=None, diff=None)

    async def execute(self, execution: ToolExecution, query: str, **kwargs: Any) -> ToolResult:
        memory = execution.ctx.services["memory"]
        count = await memory.forget(query=query)
        return ToolResult(content=f"Forgot {count} fact(s) related to '{query}'.", preview=f"Forgot {count}")
