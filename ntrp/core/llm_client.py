from collections.abc import AsyncGenerator

from ntrp.agent import CompletionResponse, ReasoningContentDelta, SpecificTool, ToolChoice, ToolChoiceMode
from ntrp.llm.models import get_model
from ntrp.llm.router import get_completion_client


def _tool_choice_to_str(tc: ToolChoice | None) -> str | dict | None:
    match tc:
        case None | ToolChoiceMode.AUTO:
            return "auto"
        case ToolChoiceMode.NONE:
            return "none"
        case ToolChoiceMode.REQUIRED:
            return "required"
        case SpecificTool(name=name):
            return {"type": "function", "function": {"name": name}}


class NtrpLLMClient:
    def _supported_reasoning_effort(self, model: str, effort: str | None) -> str | None:
        if effort is None:
            return None
        return effort if effort in get_model(model).reasoning_efforts else None

    async def stream(
        self,
        messages: list[dict],
        model: str,
        tools: list[dict],
        tool_choice: ToolChoice | None = None,
        reasoning_effort: str | None = None,
    ) -> AsyncGenerator[str | ReasoningContentDelta | CompletionResponse]:
        client = get_completion_client(model)
        reasoning_effort = self._supported_reasoning_effort(model, reasoning_effort)
        async for item in client.stream_completion(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice=_tool_choice_to_str(tool_choice),
            reasoning_effort=reasoning_effort,
        ):
            yield item

    async def complete(
        self,
        model: str,
        messages: list[dict],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> CompletionResponse:
        client = get_completion_client(model)
        kwargs: dict = {"model": model, "messages": messages}
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        return await client.completion(**kwargs)


llm_client = NtrpLLMClient()
