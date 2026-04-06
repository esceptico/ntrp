from dataclasses import dataclass

from ntrp.agent.types.tool_choice import ToolChoice


@dataclass(frozen=True)
class StepConfig:
    messages: list[dict] | None = None
    model: str | None = None
    tool_choice: ToolChoice | None = None
    tools: list[dict] | None = None
