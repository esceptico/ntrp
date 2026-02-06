from ntrp.constants import EXPLORE_TIMEOUT
from ntrp.core.isolation import IsolationLevel
from ntrp.core.prompts import EXPLORE_PROMPT
from ntrp.tools.core.base import Tool, ToolResult
from ntrp.tools.core.context import ToolExecution


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

    async def _build_prompt(self, executor) -> str:
        if not executor.memory:
            return EXPLORE_PROMPT

        user_facts, _ = await executor.memory.get_context(user_limit=5, recent_limit=0)
        if not user_facts:
            return EXPLORE_PROMPT

        context = "\n".join(f"- {f.text}" for f in user_facts)
        return f"{EXPLORE_PROMPT}\n\nUSER CONTEXT:\n{context}"

    async def execute(self, execution: ToolExecution, task: str, **kwargs) -> ToolResult:
        ctx = execution.ctx

        tools = ctx.executor.get_tools(mutates=False)
        remember_schema = ctx.executor.registry.get_schemas(names={"remember"})
        tools = tools + remember_schema

        prompt = await self._build_prompt(ctx.executor)

        result = await ctx.executor.spawn(
            ctx,
            task=task,
            system_prompt=prompt,
            tools=tools,
            timeout=EXPLORE_TIMEOUT,
            parent_id=execution.tool_id,
            isolation=IsolationLevel.FULL,
        )
        return ToolResult(result, "Explored")
