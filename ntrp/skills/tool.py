from pydantic import BaseModel, Field

from ntrp.tools.core import ToolResult, tool
from ntrp.tools.core.context import ToolExecution


class UseSkillInput(BaseModel):
    skill: str = Field(description="Name of the skill to activate")
    args: str = Field(default="", description="Optional arguments for the skill")


USE_SKILL_DESCRIPTION = (
    "Activate a skill to get specialized instructions for a task. "
    "Available skills are listed in the system prompt under <available_skills>. "
    "Use this tool with the skill name and optional arguments. "
    "When a skill matches the user's request, invoke it BEFORE generating any other response about the task."
)


async def use_skill(execution: ToolExecution, args: UseSkillInput) -> ToolResult:
    registry = execution.ctx.services["skill_registry"]
    body = registry.load_body(args.skill)
    if body is None:
        available = ", ".join(registry.names)
        return ToolResult(
            content=f"Unknown skill: {args.skill}. Available: {available}",
            preview=f"Unknown skill: {args.skill}",
            is_error=True,
        )

    meta = registry.get(args.skill)
    body = body.replace("<skill_path>", str(meta.path))
    content = f'<skill name="{args.skill}" path="{meta.path}">\n{body}\n</skill>'
    if args.args:
        content += f"\n\nARGUMENTS: {args.args}"

    return ToolResult(content=content, preview=f"Loaded skill: {args.skill}")


use_skill_tool = tool(
    display_name="UseSkill",
    description=USE_SKILL_DESCRIPTION,
    input_model=UseSkillInput,
    requires={"skill_registry"},
    execute=use_skill,
)
