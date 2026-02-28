from pydantic import BaseModel, Field

from ntrp.tools.core.base import Tool, ToolResult
from ntrp.tools.core.context import ToolExecution


class UseSkillInput(BaseModel):
    skill: str = Field(description="Name of the skill to activate")
    args: str = Field(default="", description="Optional arguments for the skill")


class UseSkillTool(Tool):
    name = "use_skill"
    display_name = "UseSkill"
    description = (
        "Activate a skill to get specialized instructions for a task. "
        "Available skills are listed in the system prompt under <available_skills>. "
        "Use this tool with the skill name and optional arguments. "
        "When a skill matches the user's request, invoke it BEFORE generating any other response about the task."
    )
    requires = frozenset({"skill_registry"})
    input_model = UseSkillInput

    async def execute(self, execution: ToolExecution, skill: str, args: str = "", **kwargs) -> ToolResult:
        registry = execution.ctx.services["skill_registry"]
        body = registry.load_body(skill)
        if body is None:
            available = ", ".join(registry.names)
            return ToolResult(
                content=f"Unknown skill: {skill}. Available: {available}",
                preview=f"Unknown skill: {skill}",
                is_error=True,
            )

        meta = registry.get(skill)
        content = f'<skill name="{skill}" path="{meta.path}">\n{body}\n</skill>'
        if args:
            content += f"\n\nARGUMENTS: {args}"

        return ToolResult(content=content, preview=f"Loaded skill: {skill}")
