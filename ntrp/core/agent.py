from collections.abc import AsyncGenerator, Callable
from typing import Any

import litellm

from ntrp.constants import SUPPORTED_MODELS
from ntrp.context.compression import compress_context_async, mask_old_tool_results, should_compress
from ntrp.core.parsing import parse_tool_calls, sanitize_assistant_message
from ntrp.core.spawner import create_spawn_fn
from ntrp.core.state import AgentState, StateCallback
from ntrp.core.tool_runner import ToolRunner
from ntrp.events import SSEEvent, TextEvent, ToolResultEvent
from ntrp.tools.core.context import ToolContext
from ntrp.tools.executor import ToolExecutor


class Agent:
    def __init__(
        self,
        tools: list[dict],
        tool_executor: ToolExecutor,
        model: str,
        system_prompt: str,
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
        self._last_input_tokens: int | None = None  # For adaptive compression

        self.ctx.spawn_fn = create_spawn_fn(
            executor=self.executor,
            model=self.model,
            max_depth=self.max_depth,
            current_depth=self.current_depth,
            cancel_check=self.cancel_check,
        )

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
        model_params = SUPPORTED_MODELS[self.model]
        return await litellm.acompletion(
            model=self.model,
            messages=self.messages,
            tools=self.tools if self.tools else None,
            tool_choice="auto" if self.tools else None,
            **model_params.get("request_kwargs", {}),
        )

    def _track_usage(self, response: Any) -> None:
        if response.usage:
            prompt_tokens = response.usage.prompt_tokens or 0
            self.total_input_tokens += prompt_tokens
            self.total_output_tokens += response.usage.completion_tokens or 0
            # Track for adaptive compression on next iteration
            self._last_input_tokens = prompt_tokens

    async def _maybe_compact(self) -> None:
        # Use actual token count from last LLM response if available (more accurate)
        if not should_compress(self.messages, self.model, self._last_input_tokens):
            return

        # Phase 1: observation masking — truncate old tool results
        self.messages = mask_old_tool_results(self.messages)

        # After masking, re-check without actual count (we modified messages)
        if not should_compress(self.messages, self.model):
            return

        # Phase 2: full summarization
        self.messages, _ = await compress_context_async(self.messages, self.model)

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

    async def stream(
        self, task: str, history: list[dict] | None = None
    ) -> AsyncGenerator[SSEEvent | str]:
        if self.current_depth >= self.max_depth:
            yield f"Max depth ({self.max_depth}) reached."
            return

        self._init_messages(task, history)
        runner = self._create_tool_runner()

        while True:
            if self._is_cancelled():
                await self._set_state(AgentState.IDLE)
                yield "Cancelled."
                return

            await self._set_state(AgentState.THINKING)
            await self._maybe_compact()

            try:
                response = await self._call_llm()
            except Exception:
                await self._set_state(AgentState.IDLE)
                raise

            message = response.choices[0].message
            self.messages.append(sanitize_assistant_message(message))
            self._track_usage(response)

            if self._is_cancelled():
                await self._set_state(AgentState.IDLE)
                yield "Cancelled."
                return

            if not message.tool_calls:
                await self._set_state(AgentState.RESPONDING)
                await self._set_state(AgentState.IDLE)
                yield message.content or ""
                return

            if message.content:
                yield TextEvent(content=message.content)

            await self._set_state(AgentState.TOOL_CALL)
            calls = parse_tool_calls(message.tool_calls)

            results: dict[str, str] = {}

            async for event in runner.execute_all(calls):
                if isinstance(event, ToolResultEvent):
                    results[event.tool_id] = event.result
                yield event

            if self._is_cancelled():
                await self._set_state(AgentState.IDLE)
                yield "Cancelled."
                return

            self._append_tool_results(message.tool_calls, results)

    async def run(self, task: str, history: list[dict] | None = None) -> str:
        result = ""
        async for item in self.stream(task, history):
            if isinstance(item, str):
                result = item
            elif isinstance(item, TextEvent):
                pass  # subagent phrases stay internal
            elif self.ctx.emit:
                await self.ctx.emit(item)
        return result
