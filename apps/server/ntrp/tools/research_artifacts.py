"""Per-run scratchpad for research subagents.

A bounded, scope-isolated artifact store so a deep-research subagent can offload
bulk (long source inventories, draft tables, working notes) out of its own
context and re-read specific parts on demand. Scoped to the subagent's run
(research_scope_id) — it cannot touch user/workspace files. The subagent returns
a distilled summary + a manifest; the bulk stays here.
"""

from pydantic import BaseModel, Field

from ntrp.tools.core import ToolResult, tool
from ntrp.tools.core.context import ToolExecution
from ntrp.tools.core.types import ToolAction, ToolPolicy, ToolScope

MAX_ARTIFACT_BYTES = 256 * 1024
MAX_ARTIFACTS_PER_SCOPE = 64
_DEFAULT_READ_CHARS = 8_000
_MAX_READ_CHARS = 20_000


class WriteResearchArtifactInput(BaseModel):
    path: str = Field(description="Relative artifact path, e.g. 'sources/inventory.md'. No absolute paths or '..'.")
    content: str = Field(description="UTF-8 text to write (overwrites any existing artifact at this path).")


class AppendResearchArtifactInput(BaseModel):
    path: str = Field(description="Relative artifact path to append to (created if absent).")
    content: str = Field(description="UTF-8 text to append.")


class ReadResearchArtifactInput(BaseModel):
    path: str = Field(description="Relative artifact path to read.")
    offset: int = Field(default=0, ge=0, description="Character offset to start from (default 0).")
    limit: int = Field(
        default=_DEFAULT_READ_CHARS,
        ge=1,
        le=_MAX_READ_CHARS,
        description=f"Max chars to return (default {_DEFAULT_READ_CHARS}, max {_MAX_READ_CHARS}). Page with offset.",
    )


class ListResearchArtifactsInput(BaseModel):
    pass


def _resolve_store(execution: ToolExecution):
    store = execution.ctx.services.get("store")
    if store is not None:
        return store
    svc = execution.ctx.services.get("session")
    return getattr(svc, "store", None) if svc else None


def _scope(execution: ToolExecution) -> str:
    return execution.ctx.run.research_scope_id or execution.ctx.run.run_id


def _validate_path(path: str) -> str | None:
    if not path.strip():
        return "path must be non-empty"
    if path.startswith("/"):
        return "path must be relative (no leading '/')"
    if ".." in path.split("/"):
        return "path must not contain '..'"
    if any(ord(c) < 32 for c in path):
        return "path must not contain control characters"
    if len(path) > 256:
        return "path too long (max 256 chars)"
    return None


def _unavailable() -> ToolResult:
    return ToolResult(content="Research artifact store unavailable.", preview="Unavailable", is_error=True)


def _invalid(err: str) -> ToolResult:
    return ToolResult(content=f"Invalid path: {err}", preview="Invalid path", is_error=True)


async def write_research_artifact(execution: ToolExecution, args: WriteResearchArtifactInput) -> ToolResult:
    if err := _validate_path(args.path):
        return _invalid(err)
    if len(args.content.encode("utf-8")) > MAX_ARTIFACT_BYTES:
        return ToolResult(content=f"Artifact too large (max {MAX_ARTIFACT_BYTES} bytes).", preview="Too large", is_error=True)
    store = _resolve_store(execution)
    if store is None:
        return _unavailable()
    scope = _scope(execution)
    existing = await store.list_research_artifacts(scope_id=scope)
    if args.path not in {a["path"] for a in existing} and len(existing) >= MAX_ARTIFACTS_PER_SCOPE:
        return ToolResult(
            content=f"Too many artifacts in this research scope (max {MAX_ARTIFACTS_PER_SCOPE}).",
            preview="Too many",
            is_error=True,
        )
    await store.put_research_artifact(scope_id=scope, path=args.path, content=args.content)
    return ToolResult(content=f"Wrote research artifact {args.path} ({len(args.content)} chars).", preview=f"Wrote {args.path}")


async def append_research_artifact(execution: ToolExecution, args: AppendResearchArtifactInput) -> ToolResult:
    if err := _validate_path(args.path):
        return _invalid(err)
    store = _resolve_store(execution)
    if store is None:
        return _unavailable()
    scope = _scope(execution)
    existing = await store.get_research_artifact(scope_id=scope, path=args.path)
    if existing is None:
        listed = await store.list_research_artifacts(scope_id=scope)
        if len(listed) >= MAX_ARTIFACTS_PER_SCOPE:
            return ToolResult(
                content=f"Too many artifacts in this research scope (max {MAX_ARTIFACTS_PER_SCOPE}).",
                preview="Too many",
                is_error=True,
            )
    new_len = len(((existing or "") + args.content).encode("utf-8"))
    if new_len > MAX_ARTIFACT_BYTES:
        return ToolResult(content=f"Artifact would exceed max size ({MAX_ARTIFACT_BYTES} bytes).", preview="Too large", is_error=True)
    await store.append_research_artifact(scope_id=scope, path=args.path, content=args.content)
    return ToolResult(content=f"Appended to {args.path} ({new_len} bytes total).", preview=f"Appended {args.path}")


async def read_research_artifact(execution: ToolExecution, args: ReadResearchArtifactInput) -> ToolResult:
    if err := _validate_path(args.path):
        return _invalid(err)
    store = _resolve_store(execution)
    if store is None:
        return _unavailable()
    content = await store.get_research_artifact(scope_id=_scope(execution), path=args.path)
    if content is None:
        return ToolResult(content=f"No research artifact at {args.path}.", preview="Not found", is_error=True)
    total = len(content)
    chunk = content[args.offset : args.offset + args.limit]
    end = args.offset + len(chunk)
    header = f"[{args.path} — {total} chars, showing {args.offset}-{end}]\n"
    footer = f"\n... [{total - end} more chars; call again with offset={end}]" if end < total else ""
    return ToolResult(content=f"{header}{chunk}{footer}", preview=f"Read {len(chunk)} of {total} chars")


async def list_research_artifacts(execution: ToolExecution, args: ListResearchArtifactsInput) -> ToolResult:
    store = _resolve_store(execution)
    if store is None:
        return _unavailable()
    artifacts = await store.list_research_artifacts(scope_id=_scope(execution))
    if not artifacts:
        return ToolResult(content="No research artifacts in this scope yet.", preview="0 artifacts")
    lines = [f"- {a['path']} ({a['byte_len']} bytes)" for a in artifacts]
    return ToolResult(content="Research artifacts:\n" + "\n".join(lines), preview=f"{len(artifacts)} artifacts")


_POLICY = ToolPolicy(action=ToolAction.READ, scope=ToolScope.INTERNAL, offload=False)

write_research_artifact_tool = tool(
    display_name="WriteResearchArtifact",
    description="Write (overwrite) a scratchpad artifact for this research run. Use to offload long source inventories, tables, or draft reports out of context; return a compact manifest instead. Scoped to this run; cannot touch user files.",
    input_model=WriteResearchArtifactInput,
    policy=_POLICY,
    execute=write_research_artifact,
)

append_research_artifact_tool = tool(
    display_name="AppendResearchArtifact",
    description="Append text to a scratchpad artifact for this research run (created if absent). Good for incrementally building a source inventory.",
    input_model=AppendResearchArtifactInput,
    policy=_POLICY,
    execute=append_research_artifact,
)

read_research_artifact_tool = tool(
    display_name="ReadResearchArtifact",
    description="Read back a scratchpad artifact you wrote earlier this research run, paging with offset/limit.",
    input_model=ReadResearchArtifactInput,
    policy=_POLICY,
    execute=read_research_artifact,
)

list_research_artifacts_tool = tool(
    display_name="ListResearchArtifacts",
    description="List the scratchpad artifacts written so far in this research run.",
    input_model=ListResearchArtifactsInput,
    policy=_POLICY,
    execute=list_research_artifacts,
)
