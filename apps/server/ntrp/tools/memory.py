"""remember() tool — the user-facing entry to the memory write seam.

A plain tool that enters the SAME admit->write path as any future writer (no
privileged shortcut): it resolves scope + builds a SourceRef, then hands a single
USER_AUTHORED claim to the shared WriteSeam (CONTRACTS.md §10). The seam runs the
reconcile half (recall + ADD/NOOP/CONTRADICT) but skips the worth-gate
(bypass_admit=True) because a user assertion is maximal-novelty.

Input is deliberately small: {fact, valid_from}. No kind/confidence/tags/entities
(v1 cruft the Stage-2 store has no columns for). provenance is fixed
USER_AUTHORED, kind fixed CLAIM. Policy is WRITE/INTERNAL with no approval gate —
memory never deletes, so there is nothing to guard. Registered only when the
"memory_write" service is present (knowledge runtime wires it when memory is
ready).
"""

from pydantic import BaseModel, Field

from ntrp.logging import get_logger
from ntrp.memory.models import Provenance, Scope, ScopeKind, SourceRef
from ntrp.memory.pipeline.retrieve import Retriever
from ntrp.memory.pipeline.types import Retrieval
from ntrp.memory.pipeline.write import WriteRequest, WriteSeam
from ntrp.tools.core import ToolResult, tool
from ntrp.tools.core.context import ToolExecution
from ntrp.tools.core.types import ToolAction, ToolPolicy, ToolScope

_logger = get_logger(__name__)

MEMORY_WRITE_SERVICE = "memory_write"
MEMORY_READ_SERVICE = "memory_read"

_RECALL_TOKEN_BUDGET = 2000


class RememberInput(BaseModel):
    fact: str = Field(
        min_length=1,
        max_length=20_000,
        description=(
            "A single durable fact to remember about the user or their world, "
            "stated plainly and self-contained (resolve pronouns inline)."
        ),
    )
    valid_from: str | None = Field(
        default=None,
        description="Optional ISO-8601 instant the fact became true; defaults to now.",
    )


def _resolve_scope(execution: ToolExecution) -> Scope:
    """Scope from the active project (PROJECT/key=project_id) else USER scope.
    Assigned from structural metadata, never LLM-inferred (CONTRACTS principle #4)."""
    project = execution.ctx.project
    if project is not None and project.project_id:
        return Scope(kind=ScopeKind.PROJECT, key=str(project.project_id))
    return Scope(kind=ScopeKind.USER)


def _source_ref(execution: ToolExecution) -> SourceRef:
    """Pointer back into the raw chat layer for this remember() call."""
    ref = f"{execution.ctx.session_id}:{execution.tool_id}"
    return SourceRef(kind="chat_turn", ref=ref)


async def remember(execution: ToolExecution, args: RememberInput) -> ToolResult:
    seam = execution.ctx.services.get(MEMORY_WRITE_SERVICE)
    if not isinstance(seam, WriteSeam):
        return ToolResult(
            content="Memory is not available.",
            preview="Memory unavailable",
            is_error=True,
        )

    request = WriteRequest(
        content=args.fact,
        scope=_resolve_scope(execution),
        provenance=Provenance.USER_AUTHORED,
        source_refs=[_source_ref(execution)],
        valid_from=args.valid_from,
        bypass_admit=True,
    )

    outcome = await seam.admit_and_write(request)
    if not outcome.written and outcome.item_id is None and "Already known" not in outcome.reason:
        # A genuine failure (empty/reconcile error), not a NOOP corroboration.
        return ToolResult(content=outcome.reason, preview="Not remembered", is_error=True)

    preview = "Remembered" if outcome.written else "Already known"
    return ToolResult(content=outcome.reason, preview=preview)


def _resolve_recall_scopes(execution: ToolExecution) -> tuple[Scope, list[Scope]]:
    """Recall scope + also_scopes, resolved structurally (never LLM-inferred).

    In a project the primary scope is the project lens and USER rides along as an
    also-scope; outside a project recall is USER-only. Mirrors the chat-side
    injection scope in services/chat.py so the tool sees the same pool.
    """
    project = execution.ctx.project
    if project is not None and project.project_id:
        return (
            Scope(kind=ScopeKind.PROJECT, key=str(project.project_id)),
            [Scope(kind=ScopeKind.USER)],
        )
    return Scope(kind=ScopeKind.USER), []


class RecallInput(BaseModel):
    query: str = Field(
        min_length=1,
        max_length=4_000,
        description=(
            "A natural-language query or goal describing what you need to recall "
            "from the user's long-term memory (e.g. a question, topic, or task)."
        ),
    )


async def recall(execution: ToolExecution, args: RecallInput) -> ToolResult:
    retriever = execution.ctx.services.get(MEMORY_READ_SERVICE)
    if not isinstance(retriever, Retriever):
        return ToolResult(
            content="Memory is not available.",
            preview="Memory unavailable",
            is_error=True,
        )

    scope, also_scopes = _resolve_recall_scopes(execution)
    result = await retriever.retrieve(
        Retrieval(
            goal=args.query,
            scope=scope,
            also_scopes=also_scopes,
            token_budget=_RECALL_TOKEN_BUDGET,
        )
    )

    if not result.rendered:
        return ToolResult(content="No relevant memory found.", preview="Nothing recalled")
    return ToolResult(content=result.rendered, preview=f"Recalled {len(result.items)} item(s)")


recall_tool = tool(
    display_name="Recall",
    description=(
        "Search the user's long-term memory for knowledge relevant to a query or "
        "goal. Returns a compact, scope-filtered bundle of recalled facts. Use "
        "when the current task needs context that may have been stored in a past "
        "session and is not already in the MEMORY CONTEXT block."
    ),
    input_model=RecallInput,
    policy=ToolPolicy(
        action=ToolAction.READ,
        scope=ToolScope.INTERNAL,
        permissions=frozenset({MEMORY_READ_SERVICE}),
    ),
    execute=recall,
)


remember_tool = tool(
    display_name="Remember",
    description=(
        "Durably remember a single fact about the user or their world. Use for "
        "stable preferences, decisions, and facts worth recalling in future "
        "sessions — not transient task state. State one self-contained fact per "
        "call. A repeat corroborates; a contradiction supersedes the old fact."
    ),
    input_model=RememberInput,
    policy=ToolPolicy(
        action=ToolAction.WRITE,
        scope=ToolScope.INTERNAL,
        permissions=frozenset({MEMORY_WRITE_SERVICE}),
    ),
    execute=remember,
)
