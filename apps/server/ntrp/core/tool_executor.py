import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

from ntrp import logging
from ntrp.agent import ToolMeta, ToolResult
from ntrp.agent.ledger import SharedLedger
from ntrp.constants import (
    DEFAULT_EXTERNAL_TOOL_TIMEOUT_SECONDS,
    NTRP_TMP_BASE,
    OFFLOAD_PREVIEW_LINES,
    OFFLOAD_THRESHOLD,
)
from ntrp.tools.core.context import ToolContext, ToolExecution
from ntrp.tools.core.types import ToolAction, ToolScope
from ntrp.tools.deferred import is_deferred_tool
from ntrp.tools.executor import ToolExecutor

LIVE_READ_TOOLS = frozenset({"list_background_tasks"})
AUDIT_PREVIEW_MAX_CHARS = 500
_logger = logging.get_logger(__name__)


def _effective_timeout_seconds(tool: Any) -> int | float | None:
    if tool.policy.timeout_seconds is not None:
        return tool.policy.timeout_seconds
    if tool.policy.scope == ToolScope.EXTERNAL:
        return DEFAULT_EXTERNAL_TOOL_TIMEOUT_SECONDS
    return None


class NtrpToolExecutor:
    def __init__(self, executor: ToolExecutor, ctx: ToolContext, ledger: SharedLedger | None = None):
        self._executor = executor
        self._ctx = ctx
        self._ledger = ledger
        self._offload_counter = 0
        self._meta_cache: dict[str, ToolMeta | None] = {}

    async def execute(self, name: str, args: dict, tool_call_id: str) -> ToolResult:
        tool = self._executor.registry.get(name)
        if not tool:
            return ToolResult(
                content=f"Unknown tool: {name}. Check available tools in the system prompt.",
                preview="Unknown tool",
            )

        if (
            self._ctx.run.deferred_tools_enabled
            and is_deferred_tool(name, self._executor.registry)
            and name not in self._ctx.run.loaded_tools
        ):
            return ToolResult(
                content=(
                    f"Tool {name!r} is deferred and has not been loaded in this run. "
                    f"Call load_tools(names=[{name!r}]) or load_tools(group=...) first, then retry."
                ),
                preview="Tool not loaded",
                is_error=True,
            )

        if self._ledger and tool.policy.action == ToolAction.READ and name not in LIVE_READ_TOOLS:
            identity = f"{name}:{json.dumps(args, sort_keys=True)}"
            already_read = await self._ledger.mark_accessed(identity)
        else:
            already_read = False

        store = self._audit_store() if tool.policy.audit else None
        if store:
            await self._record_tool_call_started(store, name, args, tool_call_id, tool.policy.action, tool.policy.scope)

        execution = ToolExecution(tool_id=tool_call_id, tool_name=name, ctx=self._ctx)
        try:
            execute = self._executor.registry.execute(name, execution, args)
            timeout_seconds = _effective_timeout_seconds(tool)
            if timeout_seconds is None:
                result = await execute
            else:
                try:
                    result = await asyncio.wait_for(execute, timeout=timeout_seconds)
                except TimeoutError:
                    result = ToolResult(content="Tool call timed out.", preview="Timed out", is_error=True)
                    if store:
                        await self._record_tool_call_finished(store, tool_call_id, "timeout", result.preview)
                    return result
        except asyncio.CancelledError:
            if store:
                await self._record_tool_call_finished(store, tool_call_id, "cancelled", None)
            raise
        except Exception:
            if store:
                await self._record_tool_call_finished(store, tool_call_id, "error", None)
            raise

        result = self._truncate_result(result, tool.policy.max_result_chars)
        if tool.policy.offload:
            result = self._maybe_offload(name, result)

        if already_read:
            result = ToolResult(
                content=f"[Already read by another agent in this run]\n{result.content}",
                preview=result.preview,
                is_error=result.is_error,
                data=result.data,
                model_content=result.model_content,
            )

        if store:
            await self._record_tool_call_finished(
                store,
                tool_call_id,
                self._audit_status(result),
                result.preview,
            )

        return result

    def _audit_store(self) -> Any | None:
        store = self._ctx.services.get("store")
        if store:
            return store

        session_service = self._ctx.services.get("session")
        return getattr(session_service, "store", None)

    def _args_hash(self, args: dict) -> str:
        serialized = json.dumps(args, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _audit_preview(self, preview: str) -> str:
        if len(preview) <= AUDIT_PREVIEW_MAX_CHARS:
            return preview
        return f"{preview[:AUDIT_PREVIEW_MAX_CHARS]}... [truncated]"

    def _audit_status(self, result: ToolResult) -> str:
        if result.is_error or result.preview == "Rejected":
            return "error"
        return "success"

    async def _record_tool_call_started(
        self,
        store: Any,
        name: str,
        args: dict,
        tool_call_id: str,
        action: Any,
        scope: Any,
    ) -> None:
        try:
            await store.record_tool_call_started(
                run_id=self._ctx.run.run_id,
                session_id=self._ctx.session_id,
                tool_call_id=tool_call_id,
                tool_name=name,
                action=str(action),
                scope=str(scope),
                args_hash=self._args_hash(args),
            )
        except Exception:
            _logger.warning("Failed to record tool call audit start", exc_info=True)

    async def _record_tool_call_finished(
        self,
        store: Any,
        tool_call_id: str,
        status: str,
        result_preview: str | None,
    ) -> None:
        try:
            await store.record_tool_call_finished(
                run_id=self._ctx.run.run_id,
                tool_call_id=tool_call_id,
                status=status,
                result_preview=self._audit_preview(result_preview) if result_preview is not None else None,
            )
        except Exception:
            _logger.warning("Failed to record tool call audit finish", exc_info=True)

    def _truncate_result(self, result: ToolResult, max_chars: int | None) -> ToolResult:
        if max_chars is None or len(result.content) <= max_chars:
            return result

        return ToolResult(
            content=f"{result.content[:max_chars]}... [truncated]",
            preview=result.preview,
            is_error=result.is_error,
            data=result.data,
            model_content=result.model_content,
        )

    def get_meta(self, name: str) -> ToolMeta | None:
        if name not in self._meta_cache:
            tool = self._executor.registry.get(name)
            self._meta_cache[name] = (
                ToolMeta(
                    name=name,
                    display_name=tool.display_name or name,
                    kind=tool.kind,
                )
                if tool
                else None
            )
        return self._meta_cache[name]

    def _maybe_offload(self, tool_name: str, result: ToolResult) -> ToolResult:
        content = result.content
        if len(content) <= OFFLOAD_THRESHOLD:
            return result

        self._offload_counter += 1
        offload_dir = Path(NTRP_TMP_BASE) / self._ctx.session_id / "results"
        offload_dir.mkdir(parents=True, exist_ok=True)
        offload_path = offload_dir / f"{tool_name}_{self._offload_counter}.txt"
        offload_path.write_text(content, encoding="utf-8")

        lines = content.split("\n")
        total = len(lines)
        preview = "\n".join(lines[:OFFLOAD_PREVIEW_LINES])
        compact = (
            f"{preview}\n\n"
            f"[{total} lines total, {total - OFFLOAD_PREVIEW_LINES} more offloaded → {offload_path}]\n"
            f"Use bash(grep -n 'pattern' '{offload_path}') to find specific content, "
            f"or read_file(path='{offload_path}', offset=N, limit=M) to read a specific section."
        )
        return ToolResult(
            content=compact,
            preview=result.preview,
            is_error=result.is_error,
            data=result.data,
            model_content=result.model_content,
        )
