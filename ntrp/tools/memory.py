from datetime import datetime

from pydantic import BaseModel, Field

from ntrp.memory.formatting import format_memory_context
from ntrp.memory.models import SourceType
from ntrp.tools.core import ToolResult, tool
from ntrp.tools.core.context import ToolExecution
from ntrp.tools.core.types import ApprovalInfo

RECALL_DESCRIPTION = """Recall stored facts from memory about a topic or entity.

WHEN TO USE:
- Before answering questions about the user, their preferences, people they know, or past conversations
- When the user references something you should know ("remember when...", "what did I say about...")
- Before asking the user something they may have already told you
- When a topic comes up that might have stored context (projects, people, plans, opinions)

Your system prompt has a small memory snapshot — recall() searches the FULL memory store which is much richer.

PREFER recall() FOR: Known facts, user preferences, stored knowledge, past context
PREFER search() FOR: Finding new info in email, files, or web pages"""

FORGET_DESCRIPTION = "Delete facts from memory by semantic search."

REMEMBER_DESCRIPTION = """Store a fact in memory for future recall.

WHEN TO USE:
- After learning something important about the user
- After discovering a key fact from email, files, or connected services
- To record user preferences or decisions

IMPORTANT: Only store facts that would be useful to recall in 6+ months.
BAD: "Python is a programming language" (not user-specific)"""


class RememberInput(BaseModel):
    fact: str = Field(description="The fact to remember (natural language).")
    source: str | None = Field(default=None, description="Where this fact came from (e.g. file path, email id).")
    happened_at: str | None = Field(
        default=None, description="ISO timestamp of when the event occurred (for temporal linking)."
    )


async def approve_remember(execution: ToolExecution, args: RememberInput) -> ApprovalInfo | None:
    return ApprovalInfo(description=args.fact[:100], preview=None, diff=None)


async def remember(execution: ToolExecution, args: RememberInput) -> ToolResult:
    memory = execution.ctx.services["memory"]
    event_time = datetime.fromisoformat(args.happened_at) if args.happened_at else None

    result = await memory.remember(
        text=args.fact,
        source_type=SourceType.CHAT,
        source_ref=args.source,
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


async def recall(execution: ToolExecution, args: RecallInput) -> ToolResult:
    memory = execution.ctx.services["memory"]
    context = await memory.recall(query=args.query, limit=args.limit)
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


async def approve_forget(execution: ToolExecution, args: ForgetInput) -> ApprovalInfo | None:
    return ApprovalInfo(description=args.query, preview=None, diff=None)


async def forget(execution: ToolExecution, args: ForgetInput) -> ToolResult:
    memory = execution.ctx.services["memory"]
    count = await memory.forget(query=args.query)
    return ToolResult(content=f"Forgot {count} fact(s) related to '{args.query}'.", preview=f"Forgot {count}")


remember_tool = tool(
    display_name="Remember",
    description=REMEMBER_DESCRIPTION,
    input_model=RememberInput,
    mutates=True,
    requires={"memory"},
    approval=approve_remember,
    execute=remember,
)

recall_tool = tool(
    display_name="Recall",
    description=RECALL_DESCRIPTION,
    input_model=RecallInput,
    requires={"memory"},
    execute=recall,
)

forget_tool = tool(
    display_name="Forget",
    description=FORGET_DESCRIPTION,
    input_model=ForgetInput,
    mutates=True,
    requires={"memory"},
    approval=approve_forget,
    execute=forget,
)
