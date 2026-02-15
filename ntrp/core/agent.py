from collections.abc import AsyncGenerator, Callable
from typing import Any

from ntrp.constants import AGENT_MAX_ITERATIONS
from ntrp.context.compression import compress_context_async, find_compressible_range, should_compress
from ntrp.core.events import ContextCompressed
from ntrp.core.parsing import normalize_assistant_message, parse_tool_calls
from ntrp.core.state import AgentState, StateCallback
from ntrp.core.tool_runner import ToolRunner
from ntrp.events import SSEEvent, TextEvent, ThinkingEvent, ToolResultEvent
from ntrp.llm.models import get_model
from ntrp.llm.router import get_completion_client
from ntrp.logging import get_logger
from ntrp.tools.core.context import ToolContext
from ntrp.tools.executor import ToolExecutor

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
        cancel_check: Callable[[], bool] | None = None,
    ):
        self.tools = tools
        self.executor = tool_executor
        self.model = model
        self.system_prompt = system_prompt
        self.max_depth = max_depth
        self.current_depth = current_depth
        self.parent_id = parent_id
        self.on_state_change = on_state_change
        self.cancel_check = cancel_check
        self.ctx = ctx

        self._state = AgentState.IDLE
        self.messages: list[dict] = []
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cache_read_tokens = 0
        self.total_cache_write_tokens = 0
        self.total_cost = 0.0
        self._last_input_tokens: int | None = None  # For adaptive compression

    @property
    def state(self) -> AgentState:
        return self._state

    async def _set_state(self, new_state: AgentState) -> None:
        if new_state != self._state:
            self._state = new_state
            if self.on_state_change:
                await self.on_state_change(new_state)

    def _is_cancelled(self) -> bool:
        return self.cancel_check is not None and self.cancel_check()

    def _init_messages(self, task: str, history: list[dict] | None) -> None:
        if history:
            self.messages = list(history)
            self.messages.append({"role": "user", "content": task})
        else:
            self.messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": task},
            ]

    async def _call_llm(self) -> Any:
        client = get_completion_client(self.model)
        return await client.completion(
            model=self.model,
            messages=self.messages,
            tools=self.tools,
            tool_choice="auto",
        )

    def _track_usage(self, response: Any) -> None:
        if not response.usage:
            return
        prompt_tokens = response.usage.prompt_tokens or 0
        completion_tokens = response.usage.completion_tokens or 0
        cache_read = response.usage.cache_read_tokens or 0
        cache_write = response.usage.cache_write_tokens or 0

        self.total_input_tokens += prompt_tokens
        self.total_output_tokens += completion_tokens
        self.total_cache_read_tokens += cache_read
        self.total_cache_write_tokens += cache_write
        self._last_input_tokens = prompt_tokens + cache_read + cache_write

        model = get_model(response.model)
        self.total_cost += (
            prompt_tokens * model.price_in
            + completion_tokens * model.price_out
            + cache_read * model.price_cache_read
            + cache_write * model.price_cache_write
        ) / 1_000_000

    async def _maybe_compact(self) -> AsyncGenerator[SSEEvent]:
        if not should_compress(self.messages, self.model, self._last_input_tokens):
            return

        if self.current_depth == 0:
            yield ThinkingEvent(status="compressing context...")

        start, end = find_compressible_range(self.messages)
        if start == 0 and end == 0:
            return

        discarded = tuple(self.messages[start:end])
        self.messages, _ = await compress_context_async(self.messages, self.model, force=True)

        if self.current_depth == 0:
            self.ctx.channel.publish(
                ContextCompressed(messages=discarded, session_id=self.ctx.session_id)
            )

    def _append_tool_results(self, tool_calls: list[Any], results: dict[str, str]) -> None:
        for tc in tool_calls:
            result = results.get(tc.id, "Error: tool execution failed")
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
            is_cancelled=self._is_cancelled,
        )

    async def stream(self, task: str, history: list[dict] | None = None) -> AsyncGenerator[SSEEvent | str]:
        if self.current_depth >= self.max_depth:
            yield f"Max depth ({self.max_depth}) reached."
            return

        self._init_messages(task, history)
        runner = self._create_tool_runner()

        iteration = 0
        while True:
            if AGENT_MAX_ITERATIONS is not None and iteration >= AGENT_MAX_ITERATIONS:
                await self._set_state(AgentState.IDLE)
                yield f"Stopped: reached max iterations ({AGENT_MAX_ITERATIONS})."
                return

            if self._is_cancelled():
                await self._set_state(AgentState.IDLE)
                yield "Cancelled."
                return

            await self._set_state(AgentState.THINKING)
            async for event in self._maybe_compact():
                yield event

            try:
                response = await self._call_llm()
            except Exception:
                _logger.exception("LLM call failed (model=%s)", self.model)
                await self._set_state(AgentState.IDLE)
                raise

            message = response.choices[0].message
            self.messages.append(normalize_assistant_message(message))
            self._track_usage(response)

            if self._is_cancelled():
                await self._set_state(AgentState.IDLE)
                yield "Cancelled."
                return

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

                if self._is_cancelled():
                    await self._set_state(AgentState.IDLE)
                    yield "Cancelled."
                    return
            finally:
                self._append_tool_results(message.tool_calls, results)

            iteration += 1

    async def run(self, task: str, history: list[dict] | None = None) -> str:
        result = ""
        async for item in self.stream(task, history):
            match item:
                case str():
                    result = item
                case TextEvent():
                    pass
                case event if self.ctx.emit:
                    await self.ctx.emit(event)
        return result
