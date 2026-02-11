from dataclasses import dataclass
from datetime import datetime

from ntrp.constants import RECALL_SEARCH_LIMIT
from ntrp.context.models import SessionData, SessionState
from ntrp.core.prompts import build_system_prompt
from ntrp.memory.formatting import format_memory_context
from ntrp.server.runtime import Runtime
from ntrp.server.state import RunState
from ntrp.skills.registry import SkillRegistry


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


async def prepare_messages(
    runtime: Runtime,
    messages: list[dict],
    user_message: str,
    last_activity: datetime | None = None,
) -> tuple[list[dict], str]:
    # Get memory context if available
    memory_context = None
    if runtime.memory:
        user_facts, recent_facts = await runtime.memory.get_context()

        # Query-conditioned recall: inject facts relevant to this specific message
        query_context = await runtime.memory.recall(user_message, limit=RECALL_SEARCH_LIMIT)
        # Deduplicate against static context
        static_ids = {f.id for f in user_facts} | {f.id for f in recent_facts}
        query_facts = [f for f in query_context.facts if f.id not in static_ids]

        formatted_memory_context = format_memory_context(
            user_facts=user_facts,
            recent_facts=recent_facts,
            query_facts=query_facts,
            query_observations=query_context.observations,
        )
        memory_context = formatted_memory_context or None

    skills_context = runtime.skill_registry.to_prompt_xml() if runtime.skill_registry else None

    system_prompt = build_system_prompt(
        source_details=runtime.get_source_details(),
        last_activity=last_activity,
        memory_context=memory_context,
        skills_context=skills_context,
    )

    if not messages:
        messages = [{"role": "system", "content": system_prompt}]
    elif isinstance(messages[0], dict) and messages[0].get("role") == "system":
        messages[0]["content"] = system_prompt
    else:
        messages.insert(0, {"role": "system", "content": system_prompt})

    messages.append({"role": "user", "content": user_message})

    return messages, system_prompt
