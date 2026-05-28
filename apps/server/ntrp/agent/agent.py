import asyncio
import time
from collections.abc import AsyncGenerator, Callable, Sequence
from dataclasses import dataclass
from uuid import uuid4

from ntrp.agent.hooks import AgentHooks
from ntrp.agent.llm.client import LLMClient
from ntrp.agent.llm.parsing import normalize_assistant_message, parse_tool_calls
from ntrp.agent.model_request import ModelRequest, ModelRequestMiddleware, apply_model_request_middlewares
from ntrp.agent.tools.dispatch import dispatch_tools
from ntrp.agent.tools.executor import AgentToolExecutor
from ntrp.agent.tools.runner import ToolRunner
from ntrp.agent.types.events import (
    ReasoningBlock,
    ReasoningDelta,
    ReasoningEnded,
    ReasoningStarted,
    Result,
    TextBlock,
    TextDelta,
    TextEnded,
    TextStarted,
    ToolCompleted,
    ToolInputDelta,
    ToolInputEnded,
    ToolInputStarted,
    ToolStarted,
)
from ntrp.agent.types.llm import CompletionResponse, ReasoningContentDelta, Role, ToolCallStreamDelta
from ntrp.agent.types.stop import StopReason
from ntrp.agent.types.tool_choice import ToolChoice, ToolChoiceMode
from ntrp.agent.types.usage import Usage

AgentEvent = (
    TextStarted
    | TextDelta
    | TextEnded
    | TextBlock
    | ReasoningBlock
    | ReasoningStarted
    | ReasoningDelta
    | ReasoningEnded
    | ToolStarted
    | ToolCompleted
    | ToolInputStarted
    | ToolInputDelta
    | ToolInputEnded
    | Result
)


@dataclass
class RunBudget:
    tool_calls: int = 0


class Agent:
    def __init__(
        self,
        tools: list[dict],
        client: LLMClient,
        executor: AgentToolExecutor,
        model: str,
        max_iterations: int | None = None,
        max_tool_calls: int | None = None,
        max_wall_time_seconds: float | None = None,
        max_cost: float | None = None,
        max_depth: int = 3,
        current_depth: int = 0,
        parent_id: str | None = None,
        tool_choice: ToolChoice = ToolChoiceMode.AUTO,
        reasoning_effort: str | None = None,
        prompt_cache_key: str | None = None,
        hooks: AgentHooks | None = None,
        model_request_middlewares: Sequence[ModelRequestMiddleware] = (),
        cost_calculator: Callable[[CompletionResponse], float] | None = None,
        cost_getter: Callable[[], float] | None = None,
        clock: Callable[[], float] = time.monotonic,
        started_at: float | None = None,
        budget: RunBudget | None = None,
    ):
        if max_cost is not None and cost_calculator is None and cost_getter is None:
            raise ValueError("max_cost requires cost_calculator or cost_getter")

        self.tools = tools
        self.client = client
        self.model = model
        self.max_iterations = max_iterations
        self.max_tool_calls = max_tool_calls
        self.max_wall_time_seconds = max_wall_time_seconds
        self.max_cost = max_cost
        self.max_depth = max_depth
        self.current_depth = current_depth
        self.parent_id = parent_id
        self.tool_choice = tool_choice
        self.reasoning_effort = reasoning_effort
        self.prompt_cache_key = prompt_cache_key
        self.hooks = hooks or AgentHooks()
        self.model_request_middlewares = tuple(model_request_middlewares)
        self.cost_calculator = cost_calculator
        self.cost_getter = cost_getter
        self._clock = clock
        self._started_at = started_at
        self._budget = budget or RunBudget()
        self._executor = executor
        self._runner = ToolRunner(executor=executor, depth=current_depth, parent_id=parent_id)
        self._last_response: CompletionResponse | None = None
        self._last_text_id: str | None = None
        self._last_streamed_tool_input_ids: set[str] = set()
        self._usage = Usage()
        self._cost = 0.0

    async def stream(self, messages: list[dict]) -> AsyncGenerator[AgentEvent]:
        if self.current_depth >= self.max_depth:
            yield self._result("", StopReason.MAX_DEPTH, 0)
            return

        started_at = self._started_at if self._started_at is not None else self._clock()
        step = 0
        result_text = ""
        try:
            while True:
                await self._drain_pending(messages)

                if self.max_iterations is not None and step >= self.max_iterations:
                    yield self._result(result_text, StopReason.MAX_ITERATIONS, step)
                    return

                if reason := self._budget_stop_reason(started_at):
                    yield self._result(result_text, reason, step)
                    return

                step_model, step_tools, step_tool_choice, step_reasoning_effort = await self._prepare(step, messages)

                if reason := self._budget_stop_reason(started_at):
                    yield self._result(result_text, reason, step)
                    return

                async for event in self._call_llm(
                    messages, step_model, step_tools, step_tool_choice, step_reasoning_effort
                ):
                    yield event

                response_message = self._last_response.choices[0].message
                if reason := self._budget_stop_reason(started_at):
                    if response_message.tool_calls:
                        self._append_budget_denials(messages, response_message.tool_calls, reason)
                    yield self._result(result_text, reason, step)
                    return

                if not response_message.tool_calls:
                    # A user message may have arrived during this LLM turn.
                    # Drain it before declaring the run finished so the agent
                    # can respond to it instead of stranding it.
                    before = len(messages)
                    await self._drain_pending(messages)
                    if len(messages) > before:
                        continue
                    result_text = (response_message.content or "").strip()
                    yield self._result(result_text, StopReason.END_TURN, step)
                    return

                if text := (response_message.content or "").strip():
                    yield TextBlock(
                        depth=self.current_depth,
                        parent_id=self.parent_id,
                        message_id=self._last_text_id,
                        content=text,
                    )

                calls = parse_tool_calls(response_message.tool_calls)
                if self._would_exceed_tool_budget(len(calls)):
                    self._append_budget_denials(messages, response_message.tool_calls, StopReason.MAX_TOOL_CALLS)
                    yield self._result(result_text, StopReason.MAX_TOOL_CALLS, step)
                    return
                self._record_tool_calls(len(calls))

                streamed_tool_input_ids = self._last_streamed_tool_input_ids
                async for event in dispatch_tools(self._runner, messages, calls, response_message.tool_calls):
                    if isinstance(event, ToolStarted) and event.tool_id in streamed_tool_input_ids:
                        continue
                    yield event

                if reason := self._budget_stop_reason(started_at):
                    yield self._result(result_text, reason, step)
                    return

                step += 1
                if self.hooks.on_step_finish:
                    await self.hooks.on_step_finish(step, self._last_response, messages)

        except asyncio.CancelledError:
            result_text = "Cancelled."
            yield self._result(result_text, StopReason.CANCELLED, step)
            raise

        finally:
            if self.hooks.on_finish:
                await self.hooks.on_finish(result_text, step, messages)

    async def run(self, messages: list[dict]) -> Result:
        result = self._result("", StopReason.END_TURN, 0)
        async for event in self.stream(messages):
            if isinstance(event, Result):
                result = event
        return result

    # -- internals --

    def _result(self, text: str, reason: StopReason, step: int) -> Result:
        return Result(text=text, stop_reason=reason, steps=step, usage=self._usage)

    def _budget_stop_reason(self, started_at: float) -> StopReason | None:
        if self.max_tool_calls is not None and self._budget.tool_calls >= self.max_tool_calls:
            return StopReason.MAX_TOOL_CALLS
        if self.max_wall_time_seconds is not None and self._clock() - started_at >= self.max_wall_time_seconds:
            return StopReason.MAX_WALL_TIME
        if self.max_cost is not None and self._current_cost() >= self.max_cost:
            return StopReason.MAX_COST
        return None

    def _current_cost(self) -> float:
        if self.cost_getter:
            return self.cost_getter()
        return self._cost

    def _would_exceed_tool_budget(self, call_count: int) -> bool:
        return self.max_tool_calls is not None and self._budget.tool_calls + call_count > self.max_tool_calls

    def _record_tool_calls(self, call_count: int) -> None:
        self._budget.tool_calls += call_count

    def _append_budget_denials(self, messages: list[dict], tool_calls, reason: StopReason) -> None:
        content = self._budget_denial_content(reason)
        for tc in tool_calls:
            messages.append({"role": Role.TOOL, "tool_call_id": tc.id, "content": content})

    def _budget_denial_content(self, reason: StopReason) -> str:
        if reason == StopReason.MAX_TOOL_CALLS:
            assert self.max_tool_calls is not None
            return f"Tool call denied: max tool-call budget of {self.max_tool_calls} would be exceeded."
        if reason == StopReason.MAX_WALL_TIME:
            return "Tool call denied: max wall-time budget exceeded."
        if reason == StopReason.MAX_COST:
            return "Tool call denied: max cost budget exceeded."
        return f"Tool call denied: {reason.value}."

    async def _drain_pending(self, messages: list[dict]) -> None:
        if not self.hooks.get_pending_messages:
            return
        pending = await self.hooks.get_pending_messages()
        if pending:
            messages.extend(pending)

    async def _prepare(self, step: int, messages: list[dict]) -> tuple[str, list[dict], ToolChoice, str | None]:
        prepared = await apply_model_request_middlewares(
            ModelRequest(
                step=step,
                messages=messages,
                model=self.model,
                tools=self.tools,
                tool_choice=self.tool_choice,
                reasoning_effort=self.reasoning_effort,
                previous_response=self._last_response,
            ),
            self.model_request_middlewares,
        )

        if prepared.messages is not messages:
            messages.clear()
            messages.extend(prepared.messages)

        return prepared.model, prepared.tools, prepared.tool_choice, prepared.reasoning_effort

    async def _call_llm(
        self,
        messages: list[dict],
        model: str,
        tools: list[dict],
        tool_choice: ToolChoice,
        reasoning_effort: str | None,
    ) -> AsyncGenerator[AgentEvent]:
        try:
            self._last_streamed_tool_input_ids = set()
            response = None
            # Stable id assigned at the start of the assistant turn. Used both
            # in the SSE `message_id` for streaming clients and persisted on
            # the saved message so callers (e.g. branching) can reference it.
            text_id = f"text-{uuid4().hex[:10]}"
            text_started = False
            text_chunks: list[str] = []
            text_ended = False
            reasoning_id = f"reasoning-{uuid4().hex[:10]}"
            reasoning_started = False
            reasoning_parts: list[str] = []
            streamed_tool_inputs: dict[int, dict[str, object]] = {}
            streamed_tool_input_ids: set[str] = set()

            def close_text(content: str | None = None) -> TextEnded | None:
                nonlocal text_ended
                if not text_started or text_ended:
                    return None
                text_ended = True
                return TextEnded(
                    depth=self.current_depth,
                    parent_id=self.parent_id,
                    message_id=text_id,
                    content="".join(text_chunks) if content is None else content,
                )

            def get_tool_input(index: int) -> dict[str, object]:
                if index not in streamed_tool_inputs:
                    streamed_tool_inputs[index] = {
                        "tool_id": None,
                        "name": None,
                        "args": "",
                        "started": False,
                        "ended": False,
                    }
                return streamed_tool_inputs[index]

            kwargs = {"tool_choice": tool_choice}
            if reasoning_effort is not None:
                kwargs["reasoning_effort"] = reasoning_effort
            if self.prompt_cache_key is not None:
                kwargs["prompt_cache_key"] = self.prompt_cache_key
            async for item in self.client.stream(messages, model, tools, **kwargs):
                if isinstance(item, str):
                    if not text_started:
                        text_started = True
                        yield TextStarted(
                            depth=self.current_depth,
                            parent_id=self.parent_id,
                            message_id=text_id,
                        )
                    text_chunks.append(item)
                    yield TextDelta(
                        depth=self.current_depth,
                        parent_id=self.parent_id,
                        message_id=text_id,
                        content=item,
                    )
                elif isinstance(item, ReasoningContentDelta):
                    content = item.content.lstrip() if not reasoning_parts else item.content
                    if not content:
                        continue
                    reasoning_parts.append(content)
                    if not reasoning_started:
                        reasoning_started = True
                        yield ReasoningStarted(
                            depth=self.current_depth,
                            parent_id=self.parent_id,
                            message_id=reasoning_id,
                        )
                    yield ReasoningDelta(
                        depth=self.current_depth,
                        parent_id=self.parent_id,
                        message_id=reasoning_id,
                        content=content,
                    )
                elif isinstance(item, ToolCallStreamDelta):
                    state = get_tool_input(item.index)
                    if item.tool_id:
                        state["tool_id"] = item.tool_id
                    if item.name:
                        state["name"] = item.name
                    if item.arguments_delta:
                        state["args"] = str(state["args"]) + item.arguments_delta

                    tool_id = state["tool_id"]
                    name = state["name"]
                    if tool_id and name and not state["started"]:
                        if event := close_text():
                            yield event
                        state["started"] = True
                        streamed_tool_input_ids.add(str(tool_id))
                        meta = self._executor.get_meta(str(name))
                        yield ToolInputStarted(
                            depth=self.current_depth,
                            parent_id=self.parent_id,
                            tool_id=str(tool_id),
                            name=str(name),
                            display_name=meta.display_name if meta else str(name),
                            kind=meta.kind if meta else "tool",
                        )
                        if args := str(state["args"]):
                            yield ToolInputDelta(
                                depth=self.current_depth,
                                parent_id=self.parent_id,
                                tool_id=str(tool_id),
                                delta=args,
                            )
                    elif item.arguments_delta and state["started"] and tool_id:
                        yield ToolInputDelta(
                            depth=self.current_depth,
                            parent_id=self.parent_id,
                            tool_id=str(tool_id),
                            delta=item.arguments_delta,
                        )

                    if item.done and state["started"] and not state["ended"] and tool_id:
                        state["ended"] = True
                        yield ToolInputEnded(
                            depth=self.current_depth,
                            parent_id=self.parent_id,
                            tool_id=str(tool_id),
                        )
                elif isinstance(item, CompletionResponse):
                    response = item
        except asyncio.CancelledError:
            if event := close_text():
                yield event
            raise
        except Exception as exc:
            if event := close_text():
                yield event
            if self.hooks.on_error:
                await self.hooks.on_error(exc)
            raise

        if response is None:
            if event := close_text():
                yield event
            raise RuntimeError("LLM stream ended without a CompletionResponse")

        for state in streamed_tool_inputs.values():
            tool_id = state["tool_id"]
            if state["started"] and not state["ended"] and tool_id:
                state["ended"] = True
                yield ToolInputEnded(
                    depth=self.current_depth,
                    parent_id=self.parent_id,
                    tool_id=str(tool_id),
                )
        self._last_streamed_tool_input_ids = streamed_tool_input_ids

        self._last_response = response
        self._usage += response.usage
        if self.cost_calculator:
            self._cost += self.cost_calculator(response)
        if reasoning_started:
            yield ReasoningEnded(depth=self.current_depth, parent_id=self.parent_id, message_id=reasoning_id)
        elif reasoning := response.choices[0].message.reasoning_content:
            yield ReasoningBlock(depth=self.current_depth, parent_id=self.parent_id, content=reasoning)
        assistant_msg = normalize_assistant_message(response.choices[0].message)
        if text_started:
            # Persist the same id we streamed, so the desktop client's
            # locally-keyed message and the saved row share an id. Branching
            # by message id then doesn't need a history refresh.
            assistant_msg["client_id"] = text_id
            self._last_text_id = text_id
        else:
            self._last_text_id = None
        messages.append(assistant_msg)
        if event := close_text(response.choices[0].message.content or ""):
            yield event
        if self.hooks.on_response:
            await self.hooks.on_response(response)
