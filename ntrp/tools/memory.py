from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from ntrp.memory.formatting import format_memory_context
from ntrp.memory.models import FactType
from ntrp.tools.core.base import Tool, ToolResult

RECALL_DESCRIPTION = """Recall stored facts from memory about a topic or entity.

WHEN TO USE:
- Retrieving previously learned information
- Checking what you know about a person/topic
- Before asking questions that may have been answered

NOTE: Your system prompt already contains relevant memory context. Only call recall() when you need facts beyond what's in MEMORY CONTEXT.

PREFER recall() FOR: Known facts, user preferences, stored knowledge
PREFER search() FOR: Finding new info in notes/emails/web pages"""

FORGET_DESCRIPTION = "Delete facts from memory by semantic search."

REMEMBER_DESCRIPTION = """Store a fact in memory for future recall.

WHEN TO USE:
- After learning something important about the user
- After discovering a key fact from notes/emails
- To record user preferences or decisions

FACT TYPES:
- "world" (default): External facts about users, people, things
  Examples: "User works at Anthropic", "User completed MATS assessment", "Alice prefers Python"
- "experience": YOUR (the agent's) own actions
  Examples: "I sent email to Alice", "I searched for MATS deadlines", "I reminded User about the meeting"

IMPORTANT: User events are WORLD facts, not experiences. "experience" is ONLY for what YOU did.

BAD: "Python is a programming language" (not user-specific)"""


class RememberInput(BaseModel):
    fact: str = Field(description="The fact to remember (natural language).")
    fact_type: str = Field(
        default="world",
        description="'world' (default) for facts about users/people/things, 'experience' ONLY for YOUR agent actions.",
        json_schema_extra={"enum": ["world", "experience"]},
    )
    source: str | None = Field(default=None, description="Where this fact came from (e.g. file path, email id).")
    happened_at: str | None = Field(
        default=None, description="ISO timestamp of when the event occurred (for temporal linking)."
    )


class RememberTool(Tool):
    name = "remember"
    description = REMEMBER_DESCRIPTION
    mutates = True
    input_model = RememberInput

    def __init__(self, memory: Any):
        self.memory = memory

    async def execute(
        self,
        execution: Any,
        fact: str = "",
        fact_type: str = "world",
        source: str | None = None,
        happened_at: str | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        if not fact:
            return ToolResult("Error: fact is required", "Missing fact")

        await execution.require_approval(fact[:100])

        event_time = datetime.fromisoformat(happened_at) if happened_at else None
        ft = FactType.EXPERIENCE if fact_type == "experience" else FactType.WORLD

        result = await self.memory.remember(
            text=fact,
            fact_type=ft,
            source_type="source" if source else "explicit",
            source_ref=source,
            happened_at=event_time,
        )

        entities = ", ".join(result.entities_extracted) if result.entities_extracted else "none"
        return ToolResult(
            f"Remembered: {result.fact.text}\nEntities: {entities}\nLinks: {result.links_created}",
            "Remembered",
        )


class RecallInput(BaseModel):
    query: str = Field(description="What to recall.")
    limit: int = Field(default=5, description="Number of seed facts (default 5).")


class RecallTool(Tool):
    name = "recall"
    description = RECALL_DESCRIPTION
    input_model = RecallInput

    def __init__(self, memory: Any):
        self.memory = memory

    async def execute(self, execution: Any, query: str, limit: int = 5, **kwargs: Any) -> ToolResult:
        context = await self.memory.recall(query=query, limit=limit)
        formatted = format_memory_context(query_facts=context.facts, query_observations=context.observations)
        if formatted:
            count = len(context.facts)
            return ToolResult(formatted, f"{count} facts")
        return ToolResult(
            "No memory found for this query. Try broader terms or use remember() to store facts first.",
            "0 facts",
        )


class ForgetInput(BaseModel):
    query: str = Field(description="Description of facts to forget.")


class ForgetTool(Tool):
    name = "forget"
    description = FORGET_DESCRIPTION
    mutates = True
    input_model = ForgetInput

    def __init__(self, memory: Any):
        self.memory = memory

    async def execute(self, execution: Any, query: str = "", **kwargs: Any) -> ToolResult:
        if not query:
            return ToolResult("Error: query is required", "Missing query")

        await execution.require_approval(query)

        count = await self.memory.forget(query=query)
        return ToolResult(f"Forgot {count} fact(s) related to '{query}'.", f"Forgot {count}")
