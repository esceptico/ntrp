from typing import Any

from pydantic import BaseModel, Field

from ntrp.tools.core.base import Tool, ToolResult
from ntrp.tools.core.context import ToolExecution

ASK_CHOICE_DESCRIPTION = "Ask the user to choose from predefined options."


class ChoiceOption(BaseModel):
    id: str
    label: str
    description: str | None = None


class AskChoiceInput(BaseModel):
    question: str = Field(description="The question to ask")
    options: list[ChoiceOption] = Field(
        description="List of options. Each option has 'id' (short key), 'label' (display text), and optional 'description'"
    )
    allow_multiple: bool = Field(default=False, description="If true, user can select multiple options. Default: false")


class AskChoiceTool(Tool):
    name = "ask_choice"
    description = ASK_CHOICE_DESCRIPTION
    mutates = False
    input_model = AskChoiceInput

    async def execute(self, execution: ToolExecution, **kwargs: Any) -> ToolResult:
        question = kwargs.get("question", "")
        options = kwargs.get("options", [])
        allow_multiple = kwargs.get("allow_multiple", False)

        if not question:
            return ToolResult("Error: question is required", "Missing question")
        if not options or len(options) < 2:
            return ToolResult("Error: at least 2 options are required", "Too few options")

        for opt in options:
            if not isinstance(opt, dict) or "id" not in opt or "label" not in opt:
                return ToolResult("Error: each option must have 'id' and 'label'", "Invalid options")

        selected = await execution.ask_choice(question, options, allow_multiple)

        if not selected:
            return ToolResult("User cancelled or no selection made", "Cancelled")

        labels = []
        for sel_id in selected:
            opt = next((o for o in options if o["id"] == sel_id), None)
            labels.append(opt["label"] if opt else sel_id)

        return ToolResult(", ".join(labels), f"Selected: {', '.join(labels)}")
