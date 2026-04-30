from pydantic import BaseModel

from ntrp.agent import Role
from ntrp.constants import CONSOLIDATION_TEMPERATURE, SESSION_HANDOFF_MARKER
from ntrp.core.prompts import env
from ntrp.llm.router import get_completion_client
from ntrp.logging import get_logger

_logger = get_logger(__name__)

CHAT_EXTRACTION_PROMPT = env.from_string("""Extract durable source-of-truth facts from this conversation.

Return facts worth remembering permanently — things useful to recall months later.
Do not write observations, patterns, summaries, or inferred profile statements. Those are derived later from facts.

EXTRACT:
- Decisions: "User chose Postgres for the project" (not both sides — just the outcome)
- Preferences: "User prefers raw SQL over ORMs"
- People and roles: "Maria leads frontend", "Artem is User's brother"
- Deadlines and commitments: "MVP deadline is March 15th"
- Personal details: locations, routines, background
- Constraints and standing rules: "User cannot share proprietary client data"
- Durable procedures only when explicitly reusable: "User runs release candidates with ./release --rc"

SKIP:
- Transient project state: current blockers, active tasks, feature requirements
- Action items: "need to add X", "should set up Y" — these are tasks, not knowledge
- Procedural steps: "ran pip install", "edited the config"
- Troubleshooting and debugging
- Tool outputs and code snippets
- Both sides of the same decision — only the outcome matters
- Inferences not directly stated in the conversation
- Patterns not directly stated: do not infer "User is X type of person" from one example
- Assistant-generated claims unless the user confirms or states them

RULES:
- Each fact must be atomic and concrete (one idea per fact)
- Use "User" for first-person references
- Only state what was explicitly said — do not infer or add context
- Prefer fewer high-quality facts over many low-quality ones
- Keep enough names, dates, project names, and constraints for provenance
- If nothing durable was discussed, return an empty list

CONVERSATION:
{{ conversation }}""")


class ChatExtractionSchema(BaseModel):
    facts: list[str] = []


def _format_messages(messages: tuple[dict, ...]) -> str:
    parts = []
    for msg in messages:
        role = msg["role"]
        if role in ("tool", "system"):
            continue
        content = msg["content"]
        if not content or not isinstance(content, str):
            continue
        if content.startswith(SESSION_HANDOFF_MARKER):
            continue
        parts.append(f"{role}: {content}")
    return "\n\n".join(parts)


async def extract_from_chat(
    messages: tuple[dict, ...],
    model: str,
) -> list[str]:
    conversation = _format_messages(messages)
    if not conversation.strip():
        return []

    prompt = CHAT_EXTRACTION_PROMPT.render(conversation=conversation)

    try:
        client = get_completion_client(model)
        response = await client.completion(
            model=model,
            messages=[{"role": Role.USER, "content": prompt}],
            response_format=ChatExtractionSchema,
            temperature=CONSOLIDATION_TEMPERATURE,
        )

        content = response.choices[0].message.content
        if not content:
            return []

        parsed = ChatExtractionSchema.model_validate_json(content)
        return parsed.facts

    except Exception:
        _logger.warning("Chat extraction failed", exc_info=True)
        return []
