import asyncio
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from ntrp.constants import AGENT_MAX_CONCURRENT
from ntrp.core.isolation import IsolationLevel
from ntrp.logging import get_logger
from ntrp.orchestra.schema import coerce, schema_instruction

_logger = get_logger(__name__)

# Global across all Orchestra instances so the cap holds under nested/concurrent
# workflows — a per-instance semaphore would let depth D run up to N*D agents.
_GLOBAL_SEM = asyncio.Semaphore(AGENT_MAX_CONCURRENT)

# Workflow workers are leaves: deny them the spawn tools so a workflow can't
# re-enter itself or fan out uncontrolled subagents (least privilege + bounds
# recursion). A workflow that needs delegation expresses it as another phase.
_WORKFLOW_EXCLUDE_TOOLS = frozenset({"workflow", "research", "background"})

WORKFLOW_AGENT_PROMPT = (
    "You are a focused worker agent inside a deterministic workflow. "
    "Do exactly the task you are given, using tools as needed, then return a "
    "concise final answer. If the task asks for JSON matching a schema, your "
    "final message must be ONLY that JSON — no prose, no markdown fences."
)

Thunk = Callable[[], Awaitable[Any]]
Stage = Callable[[Any, Any, int], Awaitable[Any]]


async def _safe(thunk: Thunk) -> Any:
    try:
        return await thunk()
    except Exception as exc:
        _logger.warning("workflow unit failed: %s", exc)
        return None


class Orchestra:
    """Deterministic subagent orchestration over ctx.spawn_fn.

    Combinators mirror the Workflow engine: agent() spawns one subagent and
    optionally coerces its text into a schema; parallel() fans out with a
    barrier; pipeline() runs per-item stage chains with no barrier. Failed units
    degrade to None — asyncio.TaskGroup cancels siblings on the first exception,
    so every unit is wrapped to swallow errors and keep the rest alive.
    """

    def __init__(self, ctx: Any, parent_id: str | None = None, workflow_id: str | None = None, name: str | None = None):
        self.ctx = ctx
        self.parent_id = parent_id
        self.workflow_id = workflow_id
        self.name = name
        self.spawn_count = 0
        self._phase: str | None = None

    @classmethod
    def for_ctx(
        cls, ctx: Any, parent_id: str | None = None, workflow_id: str | None = None, name: str | None = None
    ) -> "Orchestra":
        return cls(ctx=ctx, parent_id=parent_id, workflow_id=workflow_id, name=name)

    def phase(self, title: str) -> None:
        self._phase = title

    def log(self, message: str) -> None:
        _logger.info("[workflow] %s", message)

    async def agent(
        self,
        task: str,
        *,
        schema: type[BaseModel] | None = None,
        tools: list[dict] | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
        phase: str | None = None,
    ) -> Any:
        self.spawn_count += 1
        active_phase = phase or self._phase
        prompt = task if schema is None else f"{task}\n\n{schema_instruction(schema)}"
        text = await self._spawn(prompt, tools, model, system_prompt, active_phase)
        if schema is None:
            return text
        try:
            return coerce(text, schema)
        except Exception:
            repaired = await self._spawn(
                f"{prompt}\n\nYour previous reply did not parse as valid JSON for the "
                "schema. Reply with ONLY the JSON, no prose.",
                tools,
                model,
                system_prompt,
                active_phase,
            )
            try:
                return coerce(repaired, schema)
            except Exception as exc:
                raise ValueError(f"workflow agent could not produce valid {schema.__name__}") from exc

    async def parallel(self, thunks: list[Thunk]) -> list[Any]:
        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(_safe(thunk)) for thunk in thunks]
        return [task.result() for task in tasks]

    async def pipeline(self, items: list[Any], *stages: Stage) -> list[Any]:
        async def chain(item: Any, index: int) -> Any:
            current = item
            for stage in stages:
                current = await stage(current, item, index)
                if current is None:
                    return None
            return current

        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(_safe(lambda it=it, i=i: chain(it, i))) for i, it in enumerate(items)]
        return [task.result() for task in tasks]

    async def _spawn(
        self,
        task: str,
        tools: list[dict] | None,
        model: str | None,
        system_prompt: str | None,
        phase: str | None,
    ) -> str:
        lifecycle_id = f"{self.parent_id}:{uuid4().hex[:8]}" if self.parent_id else None
        async with _GLOBAL_SEM:
            spawn = await self.ctx.spawn_fn(
                self.ctx,
                task=task,
                system_prompt=system_prompt or WORKFLOW_AGENT_PROMPT,
                tools=tools,
                model_override=model,
                parent_id=self.parent_id,
                isolation=IsolationLevel.FULL,
                agent_type=phase or "workflow",
                lifecycle_id=lifecycle_id,
                workflow_id=self.workflow_id,
                phase=phase,
                exclude_tools=_WORKFLOW_EXCLUDE_TOOLS,
            )
        return spawn.text
