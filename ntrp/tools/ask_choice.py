from typing import Any

from ntrp.events import ChoiceEvent
from ntrp.tools.core.base import Tool, ToolResult
from ntrp.tools.core.context import ToolExecution


class AskChoiceTool(Tool):
    name = "ask_choice"
    description = "Ask the user to choose from predefined options."
    mutates = False

    @property
    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The question to ask",
                    },
                    "options": {
                        "type": "array",
                        "description": "List of options. Each option has 'id' (short key), 'label' (display text), and optional 'description'",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "label": {"type": "string"},
                                "description": {"type": "string"},
                            },
                            "required": ["id", "label"],
                        },
                    },
                    "allow_multiple": {
                        "type": "boolean",
                        "description": "If true, user can select multiple options. Default: false",
                        "default": False,
                    },
                },
                "required": ["question", "options"],
            },
        }

    async def execute(self, execution: ToolExecution, **kwargs: Any) -> ToolResult:
        question = kwargs.get("question", "")
        options = kwargs.get("options", [])
        allow_multiple = kwargs.get("allow_multiple", False)

        if not question:
            return ToolResult("Error: question is required", "Missing question")
        if not options or len(options) < 2:
            return ToolResult("Error: at least 2 options are required", "Too few options")

        # Validate options have required fields
        for opt in options:
            if not isinstance(opt, dict) or "id" not in opt or "label" not in opt:
                return ToolResult("Error: each option must have 'id' and 'label'", "Invalid options")

        # Emit choice event to UI
        if execution.ctx.emit:
            await execution.ctx.emit(
                ChoiceEvent(
                    question=question,
                    options=options,
                    allow_multiple=allow_multiple,
                    tool_id=execution.tool_id,
                )
            )

        return ToolResult("", "Asking")
