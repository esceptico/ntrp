from dataclasses import dataclass
from datetime import datetime

from ntrp.context.models import SessionData, SessionState
from ntrp.core.prompts import build_system_blocks
from ntrp.llm.models import get_model
from ntrp.llm.models import Provider
from ntrp.memory.formatting import format_session_memory
from ntrp.server.runtime import Runtime
from ntrp.server.state import RunState
from ntrp.skills.registry import SkillRegistry
from ntrp.tools.directives import load_directives


@dataclass
class ChatContext:
    runtime: Runtime
    run: RunState
    session_state: SessionState
    messages: list[dict]
    user_message: str
    is_init: bool


def expand_skill_command(message: str, registry: SkillRegistry) -> tuple[str, bool]:
    stripped = message.strip()
    if not stripped.startswith("/"):
        return message, False
    parts = stripped[1:].split(None, 1)
    skill_name = parts[0]
    args = parts[1] if len(parts) > 1 else ""
    body = registry.load_body(skill_name)
    if body is None:
        return message, False
    expanded = f'<skill name="{skill_name}">\n{body}\n</skill>'
    if args:
        expanded += f"\n\nUser request: {args}"
    return expanded, True


async def resolve_session(runtime: Runtime) -> SessionData:
    data = await runtime.restore_session()
    if not data:
        return SessionData(runtime.create_session(), [])
    return data


def _is_anthropic(model: str) -> bool:
    return get_model(model).provider == Provider.ANTHROPIC


async def prepare_messages(
    runtime: Runtime,
    messages: list[dict],
    user_message: str,
    last_activity: datetime | None = None,
) -> tuple[list[dict], list[dict]]:
    memory_context = None
    if runtime.memory:
        user_facts, recent_facts = await runtime.memory.get_context()
        memory_context = format_session_memory(user_facts, recent_facts) or None

    skills_context = runtime.skill_registry.to_prompt_xml() if runtime.skill_registry else None
    directives = load_directives()

    system_blocks = build_system_blocks(
        source_details=runtime.get_source_details(),
        last_activity=last_activity,
        memory_context=memory_context,
        skills_context=skills_context,
        directives=directives,
        use_cache_control=_is_anthropic(runtime.config.chat_model),
    )

    if not messages:
        messages = [{"role": "system", "content": system_blocks}]
    elif isinstance(messages[0], dict) and messages[0].get("role") == "system":
        messages[0]["content"] = system_blocks
    else:
        messages.insert(0, {"role": "system", "content": system_blocks})

    messages.append({"role": "user", "content": user_message})

    return messages, system_blocks
