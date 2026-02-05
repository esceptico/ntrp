from typing import Any

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

        # Ask user and wait for response
        selected = await execution.ask_choice(question, options, allow_multiple)

        if not selected:
            return ToolResult("User cancelled or no selection made", "Cancelled")

        # Return selected labels for agent context
        labels = []
        for sel_id in selected:
            opt = next((o for o in options if o["id"] == sel_id), None)
            labels.append(opt["label"] if opt else sel_id)

        return ToolResult(", ".join(labels), f"Selected: {', '.join(labels)}")
