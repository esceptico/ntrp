import asyncio
from collections.abc import AsyncGenerator

from ntrp.agent.hooks import AgentHooks
from ntrp.agent.llm.client import LLMClient
from ntrp.agent.llm.parsing import normalize_assistant_message, parse_tool_calls
from ntrp.agent.tools.dispatch import dispatch_tools
from ntrp.agent.tools.executor import AgentToolExecutor
from ntrp.agent.tools.runner import ToolRunner
from ntrp.agent.types.events import Result, TextBlock, TextDelta, ToolCompleted, ToolStarted
from ntrp.agent.types.llm import CompletionResponse
from ntrp.agent.types.stop import StopReason
from ntrp.agent.types.tool_choice import ToolChoice, ToolChoiceMode
from ntrp.agent.types.usage import Usage

AgentEvent = TextDelta | TextBlock | ToolStarted | ToolCompleted | Result


class Agent:
    def __init__(
        self,
        tools: list[dict],
        client: LLMClient,
        executor: AgentToolExecutor,
        model: str,
        max_iterations: int | None = None,
        max_depth: int = 3,
        current_depth: int = 0,
        parent_id: str | None = None,
        tool_choice: ToolChoice = ToolChoiceMode.AUTO,
        hooks: AgentHooks | None = None,
    ):
        self.tools = tools
        self.client = client
        self.model = model
        self.max_iterations = max_iterations
        self.max_depth = max_depth
        self.current_depth = current_depth
        self.parent_id = parent_id
        self.tool_choice = tool_choice
        self.hooks = hooks or AgentHooks()
        self._runner = ToolRunner(executor=executor, depth=current_depth, parent_id=parent_id)
        self._last_response: CompletionResponse | None = None
        self._usage = Usage()

    async def stream(self, messages: list[dict]) -> AsyncGenerator[AgentEvent]:
        if self.current_depth >= self.max_depth:
            yield self._result("", StopReason.MAX_DEPTH, 0)
            return

        step = 0
        result_text = ""
        try:
            while True:
                await self._drain_pending(messages)

                if self.max_iterations is not None and step >= self.max_iterations:
                    yield self._result(result_text, StopReason.MAX_ITERATIONS, step)
                    return

                step_model, step_tools, step_tool_choice = await self._prepare(step, messages)

                async for event in self._call_llm(messages, step_model, step_tools, step_tool_choice):
                    yield event

                response_message = self._last_response.choices[0].message
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
                    yield TextBlock(depth=self.current_depth, parent_id=self.parent_id, content=text)

                calls = parse_tool_calls(response_message.tool_calls)
                async for event in dispatch_tools(self._runner, messages, calls, response_message.tool_calls):
                    yield event

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

    async def _drain_pending(self, messages: list[dict]) -> None:
        if not self.hooks.get_pending_messages:
            return
        pending = await self.hooks.get_pending_messages()
        if pending:
            messages.extend(pending)

    async def _prepare(self, step: int, messages: list[dict]) -> tuple[str, list[dict], ToolChoice]:
        model = self.model
        tools = self.tools
        tool_choice = self.tool_choice

        if self.hooks.prepare_step:
            config = await self.hooks.prepare_step(step, messages, self._last_response)
            if config:
                if config.messages is not None:
                    messages.clear()
                    messages.extend(config.messages)
                if config.model is not None:
                    model = config.model
                if config.tools is not None:
                    tools = config.tools
                if config.tool_choice is not None:
                    tool_choice = config.tool_choice

        return model, tools, tool_choice

    async def _call_llm(
        self,
        messages: list[dict],
        model: str,
        tools: list[dict],
        tool_choice: ToolChoice,
    ) -> AsyncGenerator[AgentEvent]:
        try:
            response = None
            async for item in self.client.stream(messages, model, tools, tool_choice):
                if isinstance(item, str):
                    yield TextDelta(depth=self.current_depth, parent_id=self.parent_id, content=item)
                elif isinstance(item, CompletionResponse):
                    response = item
        except Exception as exc:
            if self.hooks.on_error:
                await self.hooks.on_error(exc)
            raise

        if response is None:
            raise RuntimeError("LLM stream ended without a CompletionResponse")

        self._last_response = response
        self._usage += response.usage
        messages.append(normalize_assistant_message(response.choices[0].message))
        if self.hooks.on_response:
            await self.hooks.on_response(response)
