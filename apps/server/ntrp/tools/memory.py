from pydantic import BaseModel, Field

from ntrp.knowledge.models import (
    KnowledgeObjectCreate,
    KnowledgeObjectStatus,
    KnowledgeObjectType,
)
from ntrp.memory.activation import MemoryActivationBundle, MemoryActivationRequest
from ntrp.tools.core import ToolResult, tool
from ntrp.tools.core.context import ToolExecution
from ntrp.tools.core.types import ApprovalInfo, ToolAction, ToolPolicy, ToolScope

RECALL_DESCRIPTION = """Recall stored knowledge about a topic or entity.

WHEN TO USE:
- Before answering questions about the user, their preferences, people they know, or past conversations
- When the user references something you should know ("remember when...", "what did I say about...")
- Before asking the user something they may have already told you
- When a topic comes up that might have stored context (projects, people, plans, opinions)

The system prompt has activated knowledge only — recall() searches the full knowledge store when this turn needs more.

PREFER recall() FOR: Known facts, user preferences, stored knowledge, lessons, procedures, artifacts, and past context
PREFER source tools FOR: Finding new info in email, files, or web pages; use search_text/read_file for local files"""

FORGET_DESCRIPTION = "Archive knowledge objects by semantic search."

REMEMBER_DESCRIPTION = """Store a knowledge object for future activation.

WHEN TO USE:
- After learning something important about the user
- After discovering a key fact from email, files, or connected services
- To record user preferences or decisions

IMPORTANT: Only store knowledge that would be useful to recall in 6+ months.
BAD: "Python is a programming language" (not user-specific)"""


class RememberInput(BaseModel):
    fact: str = Field(description="The knowledge to remember (natural language).")
    kind: str = Field(default="note", description="Knowledge type/scope label.")
    lifetime: str = Field(default="durable", description="How long this should remain active: durable or temporary.")
    salience: int = Field(default=0, ge=0, le=2, description="0 normal, 1 useful, 2 always-relevant.")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence in the stated fact.")
    entities: list[str] | None = Field(default=None, description="Concrete entity names in the fact, including User.")
    source: str | None = Field(default=None, description="Where this fact came from (e.g. file path, email id).")
    happened_at: str | None = Field(default=None, description="ISO timestamp of when the event occurred.")
    expires_at: str | None = Field(default=None, description="ISO timestamp when a temporary fact expires.")


async def approve_remember(execution: ToolExecution, args: RememberInput) -> ApprovalInfo | None:
    return ApprovalInfo(description=args.fact[:100], preview=None, diff=None)


async def remember(execution: ToolExecution, args: RememberInput) -> ToolResult:
    memory = execution.ctx.services["memory"]
    project = execution.ctx.project
    scope = project.knowledge_scope if project and project.knowledge_scope else args.kind
    obj = await memory.knowledge_objects.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.FACT,
            title=args.fact[:100],
            text=args.fact,
            status=KnowledgeObjectStatus.ACTIVE,
            scope=scope,
            activation="prompt",
            proactiveness_level="L0",
            score=args.salience * 0.2,
            source_ids=[args.source] if args.source else [],
            metadata={
                "kind": args.kind,
                "project_id": project.project_id if project else None,
                "lifetime": args.lifetime,
                "salience": args.salience,
                "confidence": args.confidence,
                "entities": args.entities or [],
                "happened_at": args.happened_at,
                "expires_at": args.expires_at,
                "tool": "remember",
            },
        )
    )

    return ToolResult(
        content=f"Remembered knowledge #{obj.id}: {obj.text}\nScope: {obj.scope}\nStatus: {obj.status}",
        preview="Remembered",
    )


_DEFAULT_RECALL_LIMIT = 5


class RecallInput(BaseModel):
    query: str = Field(description="What to recall.")
    limit: int = Field(
        default=_DEFAULT_RECALL_LIMIT, description=f"Number of seed facts (default {_DEFAULT_RECALL_LIMIT})."
    )


def _activation_bundle_payload(bundle: MemoryActivationBundle) -> dict:
    return bundle.model_dump(mode="json")


async def recall(execution: ToolExecution, args: RecallInput) -> ToolResult:
    retrieval = execution.ctx.services["memory_retrieval"]
    project = execution.ctx.project
    bundle = await retrieval.search(
        MemoryActivationRequest(
            query=args.query,
            scope=project.knowledge_scope if project else None,
            limit=args.limit,
            task="recall_tool",
            task_id=execution.tool_id,
            session_id=execution.ctx.session_id,
            run_id=execution.ctx.run.run_id,
            surface="tool",
            record_access=True,
        )
    )
    payload = _activation_bundle_payload(bundle)
    if bundle.prompt_context:
        return ToolResult(
            content=bundle.prompt_context,
            preview=f"{len(bundle.candidates)} memory items",
            data={"activation_bundle": payload},
        )
    return ToolResult(
        content="No knowledge found for this query. Try broader terms or use remember() to store durable knowledge first.",
        preview="0 memory items",
        data={"activation_bundle": payload},
    )


class ForgetInput(BaseModel):
    query: str = Field(description="Description of facts to forget.")


async def approve_forget(execution: ToolExecution, args: ForgetInput) -> ApprovalInfo | None:
    return ApprovalInfo(description=args.query, preview=None, diff=None)


async def forget(execution: ToolExecution, args: ForgetInput) -> ToolResult:
    retrieval = execution.ctx.services["memory_retrieval"]
    bundle = await retrieval.search(
        MemoryActivationRequest(
            query=args.query,
            limit=20,
            task="forget_tool",
            task_id=execution.tool_id,
            session_id=execution.ctx.session_id,
            run_id=execution.ctx.run.run_id,
            surface="tool",
        )
    )
    count = 0
    for candidate in bundle.candidates:
        cursor = await retrieval.conn.execute(
            "UPDATE memory_items SET status = 'archived', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (candidate.item_id,),
        )
        count += cursor.rowcount if cursor.rowcount > 0 else 0
    await retrieval.conn.commit()
    return ToolResult(
        content=f"Archived {count} memory item(s) related to '{args.query}'.", preview=f"Archived {count}"
    )


remember_tool = tool(
    display_name="Remember",
    description=REMEMBER_DESCRIPTION,
    input_model=RememberInput,
    policy=ToolPolicy(
        action=ToolAction.WRITE,
        scope=ToolScope.INTERNAL,
        requires_approval=True,
        permissions=frozenset({"memory"}),
    ),
    approval=approve_remember,
    execute=remember,
)

recall_tool = tool(
    display_name="Recall",
    description=RECALL_DESCRIPTION,
    input_model=RecallInput,
    policy=ToolPolicy(action=ToolAction.READ, scope=ToolScope.INTERNAL, permissions=frozenset({"memory"})),
    execute=recall,
)

forget_tool = tool(
    display_name="Forget",
    description=FORGET_DESCRIPTION,
    input_model=ForgetInput,
    policy=ToolPolicy(
        action=ToolAction.WRITE,
        scope=ToolScope.INTERNAL,
        requires_approval=True,
        permissions=frozenset({"memory"}),
    ),
    approval=approve_forget,
    execute=forget,
)
