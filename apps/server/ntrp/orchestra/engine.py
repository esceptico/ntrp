import asyncio
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from ntrp.constants import AGENT_MAX_CONCURRENT
from ntrp.core.agent_types import resolve_agent_type
from ntrp.core.isolation import IsolationLevel
from ntrp.logging import get_logger
from ntrp.orchestra.schema import model_from_schema, structured_output_tool

_logger = get_logger(__name__)

# Global across all Orchestra instances so the cap holds under nested/concurrent
# workflows — a per-instance semaphore would let depth D run up to N*D agents.
_GLOBAL_SEM = asyncio.Semaphore(AGENT_MAX_CONCURRENT)

# Runaway guard for dynamic/looping scripts: one workflow can't spawn more than
# this many agents. (A pure-Python loop with no spawns is still bounded by the
# run's wall-time/cost budget and the tool's caller.)
_MAX_WORKFLOW_SPAWNS = 200

# Workflow workers are leaves: deny them the spawn tools so a workflow can't
# re-enter itself or fan out uncontrolled subagents (least privilege + bounds
# recursion). A workflow that needs delegation expresses it as another phase.
_WORKFLOW_EXCLUDE_TOOLS = frozenset({"workflow", "research", "background"})

WORKFLOW_AGENT_PROMPT = (
    "You are a focused worker agent inside a deterministic workflow. "
    "Do exactly the task you are given, using tools as needed, then return a "
    "concise final answer."
)

# Appended to the system prompt only when a schema is requested — a prose worker
# (no schema) is never told to call structured_output.
_STRUCTURED_OUTPUT_NOTE = (
    "Provide your final answer by calling the `structured_output` tool exactly once, "
    "instead of writing it as prose."
)

Thunk = Callable[[], Awaitable[Any]]
# A parallel unit may be a bare awaitable (e.g. agent("x")) or a thunk that
# returns one (() => agent("x")). Accepting both keeps dynamic scripts simple —
# `parallel([agent(a), agent(b)])` reads naturally, no lambdas required.
Unit = Awaitable[Any] | Thunk
Stage = Callable[[Any, Any, int], Awaitable[Any]]


class WorkflowSpawnLimit(RuntimeError):
    """Raised when the per-run spawn cap is hit. Distinct so _safe re-raises it
    instead of degrading the runaway guard into a silent None."""


class WorkflowBudgetExceeded(RuntimeError):
    """Raised when the run's output-token ceiling is hit before a spawn. Like
    WorkflowSpawnLimit, _safe re-raises it so a fan-out aborts instead of
    silently degrading to None."""


class WorkflowStructuredOutputMissing(RuntimeError):
    """Raised when an agent given a schema never called structured_output. A
    workflow asking for structure and getting none is a contract violation, so
    _safe re-raises it rather than degrading to None — we do NOT parse prose."""


class TokenBudget:
    """Read-through view of the run's shared RunBudget, handed to dynamic scripts
    as `budget`. `spent()` re-reads the live shared counter on every call, so a
    script can scale fan-out to what's left: `while budget.total and
    budget.remaining() > 50_000: ...`."""

    def __init__(self, budget: Any):
        self._b = budget

    @property
    def total(self) -> int | None:
        return None if self._b is None else self._b.total

    def spent(self) -> int:
        return 0 if self._b is None else self._b.output_tokens

    def remaining(self) -> float:
        if self._b is None or self._b.total is None:
            return float("inf")
        return max(0, self._b.total - self._b.output_tokens)


async def _safe(unit: Unit) -> Any:
    try:
        return await (unit() if callable(unit) else unit)
    except (WorkflowSpawnLimit, WorkflowBudgetExceeded, WorkflowStructuredOutputMissing):
        # Resource guards + the structured-output contract must abort the whole
        # fan-out, not be swallowed into a None the model reads as a partial fail.
        raise
    except Exception as exc:
        _logger.warning("workflow unit failed: %s", exc)
        return None


class Orchestra:
    """Deterministic subagent orchestration over ctx.spawn_fn.

    Combinators mirror the Workflow engine: agent() spawns one subagent and,
    when given a schema, returns the validated args of its structured_output
    tool call; parallel() fans out with a barrier; pipeline() runs per-item
    stage chains with no barrier. Failed units
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
        # The run's shared RunBudget (same instance as the parent agent + every
        # spawned child), so spent() reflects the whole turn. None when the ctx
        # has no run (test stubs that don't exercise budgeting).
        run = getattr(ctx, "run", None)
        self._budget = getattr(run, "budget", None)
        self.budget_view = TokenBudget(self._budget)

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
        schema: Any = None,
        tools: list[dict] | list[str] | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
        agent_type: str | None = None,
        phase: str | None = None,
    ) -> Any:
        active_phase = phase or self._phase
        # agent_type resolves a shared AgentType: a tool profile (capability +
        # excludes + extra tools) and a persona prompt. An explicit system_prompt /
        # tools the script passes still win over the persona's.
        spec = resolve_agent_type(agent_type) if agent_type else None
        prompt = system_prompt or (spec.prompt if spec else None) or WORKFLOW_AGENT_PROMPT
        actions = spec.actions if spec else None
        type_exclude = spec.exclude if spec else frozenset()
        type_extra = dict(spec.extra_tools) if spec else {}
        label = agent_type or active_phase

        if schema is None:
            return await self._spawn(
                task, tools, model, prompt, active_phase,
                agent_type_label=label, actions=actions, type_exclude=type_exclude,
                extra_tools=type_extra or None,
            )

        # Structured output: the worker calls a `structured_output` tool whose input
        # model IS the schema. Its args are pydantic-validated at the tool boundary
        # (a bad shape is a cheap in-run retry, not a re-spawn) and become the
        # result — no JSON in the chat message, no string parsing of prose.
        out_model = model_from_schema(schema)
        sink: list[Any] = []
        extra_tools = {**type_extra, "structured_output": structured_output_tool(out_model, sink)}
        sys_prompt = f"{prompt}\n\n{_STRUCTURED_OUTPUT_NOTE}"
        # A name allowlist must include the tool, or the spawner filters it out.
        use_tools = tools
        if tools and all(isinstance(t, str) for t in tools) and "structured_output" not in tools:
            use_tools = [*tools, "structured_output"]

        await self._spawn(
            task, use_tools, model, sys_prompt, active_phase,
            agent_type_label=label, actions=actions, type_exclude=type_exclude, extra_tools=extra_tools,
        )
        if not sink:
            # One nudge — the model has its answer, it just didn't call the tool.
            await self._spawn(
                f"{task}\n\nYou did not call structured_output. Call it now with your final answer.",
                use_tools,
                model,
                sys_prompt,
                active_phase,
                agent_type_label=label,
                actions=actions,
                type_exclude=type_exclude,
                extra_tools=extra_tools,
            )
        if not sink:
            raise WorkflowStructuredOutputMissing(
                "workflow agent did not call structured_output for the requested schema"
            )
        result = sink[-1]
        # Preserve the contract: a pydantic schema returns the validated instance;
        # a dict schema returns a dict.
        return result if out_model is schema else result.model_dump()

    async def parallel(self, units: list[Unit]) -> list[Any]:
        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(_safe(unit)) for unit in units]
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
        tools: list[dict] | list[str] | None,
        model: str | None,
        system_prompt: str | None,
        phase: str | None,
        agent_type_label: str | None = None,
        actions: frozenset | None = None,
        type_exclude: frozenset[str] = frozenset(),
        extra_tools: dict[str, Any] | None = None,
    ) -> str:
        # Cap + count every real spawn here (not in agent()), so schema-repair
        # respawns also count toward — and are bounded by — the runaway guard.
        if self.spawn_count >= _MAX_WORKFLOW_SPAWNS:
            raise WorkflowSpawnLimit(f"workflow exceeded {_MAX_WORKFLOW_SPAWNS} agent spawns (runaway guard)")
        # Hard token ceiling: don't start a new agent once the run's shared budget
        # is spent. The spawned child shares this RunBudget, so this bounds the
        # whole fan-out (a soft-hard cap — in-flight steps may overshoot by one).
        if self._budget is not None and self._budget.total is not None and self._budget.output_tokens >= self._budget.total:
            raise WorkflowBudgetExceeded(
                f"workflow output-token budget of {self._budget.total} exhausted "
                f"({self._budget.output_tokens} spent)"
            )
        self.spawn_count += 1
        lifecycle_id = f"{self.parent_id}:{uuid4().hex[:8]}" if self.parent_id else None
        async with _GLOBAL_SEM:
            spawn = await self.ctx.spawn_fn(
                self.ctx,
                task=task,
                system_prompt=system_prompt,
                tools=tools,
                model_override=model,
                parent_id=self.parent_id,
                isolation=IsolationLevel.FULL,
                agent_type=agent_type_label or phase or "workflow",
                lifecycle_id=lifecycle_id,
                workflow_id=self.workflow_id,
                phase=phase,
                actions=actions,
                exclude_tools=_WORKFLOW_EXCLUDE_TOOLS | type_exclude,
                extra_tools=extra_tools,
            )
        return spawn.text
