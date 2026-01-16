from ntrp.constants import EXPLORE_ITERATIONS, EXPLORE_TIMEOUT
from ntrp.core.prompts import EXPLORE_PROMPT
from ntrp.tools.core import Tool, ToolExecution, ToolResult


class ExploreTool(Tool):
    name = "explore"
    description = (
        "Spawn an exploration agent for information gathering. "
        "Can run in parallel (call multiple in one turn) and nest recursively."
    )

    @property
    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "What to explore or research.",
                    },
                },
                "required": ["task"],
            },
        }

    async def execute(self, execution: ToolExecution, task: str, **kwargs) -> ToolResult:
        ctx = execution.ctx

        tools = ctx.executor.get_tools(mutates=False)
        remember_schema = ctx.executor.registry.get_schemas(names={"remember"})
        tools = tools + remember_schema

        result = await ctx.executor.spawn(
            ctx,
            task=task,
            system_prompt=EXPLORE_PROMPT,
            tools=tools,
            max_iterations=EXPLORE_ITERATIONS,
            timeout=EXPLORE_TIMEOUT,
            parent_id=execution.tool_id,
        )
        return ToolResult(result, "Explored")
