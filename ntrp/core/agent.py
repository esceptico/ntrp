import asyncio
from collections.abc import AsyncGenerator

from ntrp.constants import AGENT_MAX_ITERATIONS
from ntrp.core.compactor import Compactor
from ntrp.core.parsing import normalize_assistant_message, parse_tool_calls
from ntrp.core.state import AgentState, StateCallback
from ntrp.core.tool_runner import ToolRunner
from ntrp.events.internal import ContextCompressed
from ntrp.events.sse import BackgroundTaskEvent, SSEEvent, TextDeltaEvent, TextEvent, ToolResultEvent
from ntrp.llm.models import get_model
from ntrp.llm.router import get_completion_client
from ntrp.llm.types import CompletionResponse, ToolCall
from ntrp.logging import get_logger
from ntrp.tools.core.context import ToolContext
from ntrp.tools.executor import ToolExecutor
from ntrp.usage import Usage

_logger = get_logger(__name__)


class Agent:
    def __init__(
        self,
        tools: list[dict],
        tool_executor: ToolExecutor,
        model: str,
        system_prompt: str | list[dict],
        ctx: ToolContext,
        max_depth: int = 3,
        current_depth: int = 0,
        parent_id: str | None = None,
        on_state_change: StateCallback | None = None,
        compactor: Compactor | None = None,
    ):
        self.tools = tools
        self.executor = tool_executor
        self.model = model
        self.system_prompt = system_prompt
        self.max_depth = max_depth
        self.current_depth = current_depth
        self.parent_id = parent_id
        self.on_state_change = on_state_change
        self.ctx = ctx
        self.compactor = compactor

        self._state = AgentState.IDLE
        self.messages: list[dict] = []
        self.inject_queue: list[dict] = []
        self.usage = Usage()
        self._last_input_tokens: int | None = None

    @property
    def state(self) -> AgentState:
        return self._state

    async def _set_state(self, new_state: AgentState) -> None:
        if new_state != self._state:
            self._state = new_state
            if self.on_state_change:
                await self.on_state_change(new_state)

    def _init_messages(self, task: str, history: list[dict] | None) -> None:
        self.messages.clear()
        if history:
            self.messages.extend(history)
            self.messages.append({"role": "user", "content": task})
        else:
            self.messages.extend(
                [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": task},
                ]
            )

    async def _call_llm(self) -> CompletionResponse:
        client = get_completion_client(self.model)
        return await client.completion(
            model=self.model,
            messages=self.messages,
            tools=self.tools,
            tool_choice="auto",
        )

    async def _stream_llm(self) -> AsyncGenerator[TextDeltaEvent | CompletionResponse]:
        client = get_completion_client(self.model)
        async for item in client.stream_completion(
            model=self.model,
            messages=self.messages,
            tools=self.tools,
            tool_choice="auto",
        ):
            if isinstance(item, str):
                yield TextDeltaEvent(content=item)
            elif isinstance(item, CompletionResponse):
                yield item

    def _track_usage(self, response: CompletionResponse) -> None:
        if not response.usage:
            return
        model = get_model(response.model)
        step = response.usage.with_cost(model.pricing)
        self.usage += step
        self._last_input_tokens = step.prompt_tokens + step.cache_read_tokens + step.cache_write_tokens

    async def _maybe_compact(self) -> tuple[dict, ...]:
        if not self.compactor:
            return ()

        before = len(self.messages)
        compacted = await self.compactor.maybe_compact(self.messages, self.model, self._last_input_tokens)
        if compacted is None:
            return ()

        # Messages removed are those between system (index 0) and the kept tail.
        # The kept tail length = len(compacted) - 2 (system + handoff summary).
        kept_tail = len(compacted) - 2
        discarded = tuple(self.messages[1 : before - kept_tail])
        self.messages.clear()
        self.messages.extend(compacted)
        return discarded

    def _append_tool_results(self, tool_calls: list[ToolCall], results: dict[str, str]) -> None:
        for tc in tool_calls:
            if (result := results.get(tc.id)) is None:
                _logger.error("Missing result for tool call %s", tc.id)
                result = "Error: tool execution failed"
            self.messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                }
            )

    def _create_tool_runner(self) -> ToolRunner:
        return ToolRunner(
            executor=self.executor,
            ctx=self.ctx,
            depth=self.current_depth,
            parent_id=self.parent_id,
        )

    async def stream(self, task: str, history: list[dict] | None = None) -> AsyncGenerator[SSEEvent | str]:
        if self.current_depth >= self.max_depth:
            yield f"Max depth ({self.max_depth}) reached."
            return

        self._init_messages(task, history)
        runner = self._create_tool_runner()

        iteration = 0
        try:
            while True:
                # Drain injected messages at safe turn boundary
                if self.inject_queue:
                    self.messages.extend(self.inject_queue)
                    self.inject_queue.clear()

                if AGENT_MAX_ITERATIONS is not None and iteration >= AGENT_MAX_ITERATIONS:
                    await self._set_state(AgentState.IDLE)
                    yield f"Stopped: reached max iterations ({AGENT_MAX_ITERATIONS})."
                    return

                await self._set_state(AgentState.THINKING)

                discarded = await self._maybe_compact()
                if discarded and self.current_depth == 0:
                    self.ctx.channel.publish(ContextCompressed(messages=discarded, session_id=self.ctx.session_id))

                try:
                    response = None
                    async for item in self._stream_llm():
                        if isinstance(item, TextDeltaEvent):
                            yield item
                        else:
                            response = item
                except Exception:
                    _logger.exception("LLM call failed (model=%s)", self.model)
                    await self._set_state(AgentState.IDLE)
                    raise

                message = response.choices[0].message
                self.messages.append(normalize_assistant_message(message))
                self._track_usage(response)

                if not message.tool_calls:
                    await self._set_state(AgentState.RESPONDING)
                    await self._set_state(AgentState.IDLE)
                    yield (message.content or "").strip()
                    return

                if text := (message.content or "").strip():
                    yield TextEvent(content=text)

                await self._set_state(AgentState.TOOL_CALL)
                calls = parse_tool_calls(message.tool_calls)

                results: dict[str, str] = {}

                try:
                    async for event in runner.execute_all(calls):
                        if isinstance(event, ToolResultEvent):
                            results[event.tool_id] = event.result
                        yield event
                except asyncio.CancelledError:
                    self._append_tool_results(message.tool_calls, results)
                    raise
                else:
                    self._append_tool_results(message.tool_calls, results)

                iteration += 1
        except asyncio.CancelledError:
            cancelled_tasks = self.ctx.background_tasks.cancel_all()
            if self.ctx.io.emit and cancelled_tasks:
                for task_id, command in cancelled_tasks:
                    await self.ctx.io.emit(BackgroundTaskEvent(task_id=task_id, command=command, status="cancelled"))
            await self._set_state(AgentState.IDLE)
            yield "Cancelled."

    async def run(self, task: str, history: list[dict] | None = None) -> str:
        result = ""
        async for item in self.stream(task, history):
            match item:
                case str():
                    result = item
                case TextEvent() | TextDeltaEvent():
                    pass
                case event if self.ctx.io.emit:
                    await self.ctx.io.emit(event)
        return result
