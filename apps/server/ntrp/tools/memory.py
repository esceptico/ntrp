"""Memory tools — the agent's ONLY entry to the record layer.

Plain tools over the flat RecordStore (atomic, self-contained records in
`config.memory_db_path`):

- remember(text, kind?) -> RecordStore.add (write a record)
- forget(query)         -> hybrid-search records, delete the best hit
- recall(query)         -> hybrid record search (READ)

There is NO lens tool — lenses are USER/system concepts maintained via REST and
the dreamer, not an agent tool. Records are one flat pool: no scope, no project
partition. Each tool only appears once `MEMORY_RECORDS_SERVICE` is wired by the
knowledge runtime, so they stay hidden when memory is off.

Self-correcting interface (the standing lesson): `forget` never requires the model
to reproduce an opaque id — it searches by NL query and, on a near-miss, lists the
other candidates instead of dead-ending.
"""

from pydantic import BaseModel, Field

from ntrp.logging import get_logger
from ntrp.memory.models import SourceRef
from ntrp.tools.core import ToolResult, tool
from ntrp.tools.core.context import ToolExecution
from ntrp.tools.core.types import ToolAction, ToolPolicy, ToolScope

_logger = get_logger(__name__)

MEMORY_RECORDS_SERVICE = "memory_records"


class RememberInput(BaseModel):
    text: str = Field(
        min_length=1,
        max_length=20_000,
        description=(
            "A single durable, self-contained statement to remember about the "
            "user or their world, stated plainly (resolve pronouns inline)."
        ),
    )
    kind: str = Field(
        default="note",
        description=(
            "The record's function: fact | action | preference | note. Typed by "
            "function, not subject. Defaults to note; any short label is accepted."
        ),
    )


class ForgetInput(BaseModel):
    query: str = Field(
        min_length=1,
        max_length=20_000,
        description=(
            "A natural-language description of the memory to forget. The "
            "best-matching record is removed (no id required)."
        ),
    )


class RecallInput(BaseModel):
    query: str = Field(
        min_length=1,
        max_length=20_000,
        description="A natural-language query; returns the most relevant records.",
    )


def _unavailable() -> ToolResult:
    return ToolResult(
        content="Memory is not available.",
        preview="Memory unavailable",
        is_error=True,
    )


def _render_records(records: list) -> str:
    return "\n".join(f"- [{r.kind}] {r.text}" for r in records)


async def remember(execution: ToolExecution, args: RememberInput) -> ToolResult:
    store = execution.ctx.services.get(MEMORY_RECORDS_SERVICE)
    if store is None:
        return _unavailable()

    source = SourceRef(
        kind="chat_turn", ref=f"{execution.ctx.session_id}:{execution.tool_id}"
    )
    await store.add(args.text, kind=args.kind, source_ref=source)
    return ToolResult(content="Remembered", preview="Remembered")


async def forget(execution: ToolExecution, args: ForgetInput) -> ToolResult:
    store = execution.ctx.services.get(MEMORY_RECORDS_SERVICE)
    if store is None:
        return _unavailable()

    hits = await store.search(args.query, limit=5)
    if not hits:
        return ToolResult(content="No matching memory to forget.", preview="Not found")

    best = hits[0]
    await store.delete(best.id)
    others = hits[1:]
    content = f"Forgot: {best.text}"
    if others:
        # Self-correcting: show what else matched so the model can refine rather
        # than dead-end if it meant a different record.
        content += "\n\nOther matches (not removed):\n" + _render_records(others)
    return ToolResult(content=content, preview="Forgotten")


async def recall(execution: ToolExecution, args: RecallInput) -> ToolResult:
    store = execution.ctx.services.get(MEMORY_RECORDS_SERVICE)
    if store is None:
        return _unavailable()

    hits = await store.search(args.query, limit=10)
    if not hits:
        return ToolResult(content="No matching memory.", preview="No matches")
    return ToolResult(content=_render_records(hits), preview=f"{len(hits)} match(es)")


remember_tool = tool(
    display_name="Remember",
    description=(
        "Durably remember a single self-contained statement about the user or "
        "their world. Use for stable preferences, decisions, and facts worth "
        "recalling in future sessions — not transient task state. State one "
        "statement per call; set `kind` to its function "
        "(fact | action | preference | note)."
    ),
    input_model=RememberInput,
    policy=ToolPolicy(
        action=ToolAction.WRITE,
        scope=ToolScope.INTERNAL,
        permissions=frozenset({MEMORY_RECORDS_SERVICE}),
    ),
    execute=remember,
)

forget_tool = tool(
    display_name="Forget",
    description=(
        "Remove a previously-remembered record from long-term memory. Describe "
        "what to forget in natural language; the best-matching record is removed."
    ),
    input_model=ForgetInput,
    policy=ToolPolicy(
        action=ToolAction.WRITE,
        scope=ToolScope.INTERNAL,
        permissions=frozenset({MEMORY_RECORDS_SERVICE}),
    ),
    execute=forget,
)

recall_tool = tool(
    display_name="Recall",
    description=(
        "Search long-term memory for records relevant to a natural-language "
        "query (hybrid lexical + semantic). Read-only; use it to look up what "
        "the user has decided, prefers, or done before."
    ),
    input_model=RecallInput,
    policy=ToolPolicy(
        action=ToolAction.READ,
        scope=ToolScope.INTERNAL,
        permissions=frozenset({MEMORY_RECORDS_SERVICE}),
    ),
    execute=recall,
)
