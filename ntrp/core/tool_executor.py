import json
from pathlib import Path

from ntrp.agent import ToolMeta, ToolResult
from ntrp.agent.ledger import SharedLedger
from ntrp.constants import NTRP_TMP_BASE, OFFLOAD_PREVIEW_LINES, OFFLOAD_THRESHOLD
from ntrp.tools.core.context import ToolContext, ToolExecution
from ntrp.tools.executor import ToolExecutor


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

        if self._ledger and not tool.mutates and not tool.volatile:
            identity = f"{name}:{json.dumps(args, sort_keys=True)}"
            already_read = await self._ledger.mark_accessed(identity)
        else:
            already_read = False

        execution = ToolExecution(tool_id=tool_call_id, tool_name=name, ctx=self._ctx)
        result = await self._executor.registry.execute(name, execution, args)
        result = self._maybe_offload(name, result)

        if already_read:
            result = ToolResult(
                content=f"[Already read by another agent in this run]\n{result.content}",
                preview=result.preview,
                data=result.data,
            )

        return result

    def get_meta(self, name: str) -> ToolMeta | None:
        if name not in self._meta_cache:
            tool = self._executor.registry.get(name)
            self._meta_cache[name] = (
                ToolMeta(name=tool.name, display_name=tool.display_name, mutates=tool.mutates, volatile=tool.volatile)
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
        return ToolResult(content=compact, preview=result.preview, data=result.data)
