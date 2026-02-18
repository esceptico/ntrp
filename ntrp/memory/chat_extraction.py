from collections.abc import Callable

from pydantic import BaseModel

from ntrp.channel import Handler
from ntrp.constants import CONSOLIDATION_TEMPERATURE
from ntrp.events.internal import ContextCompressed
from ntrp.llm.router import get_completion_client
from ntrp.logging import get_logger
from ntrp.memory.facts import FactMemory

_logger = get_logger(__name__)

CHAT_EXTRACTION_PROMPT = """Extract durable personal knowledge from this conversation.

Return facts worth remembering permanently — things useful to recall months later.

EXTRACT:
- Decisions: "User chose Postgres for the project" (not both sides — just the outcome)
- Preferences: "User prefers raw SQL over ORMs"
- People and roles: "Maria leads frontend", "Artem is User's brother"
- Deadlines and commitments: "MVP deadline is March 15th"
- Personal details: locations, routines, background

SKIP:
- Transient project state: current blockers, active tasks, feature requirements
- Action items: "need to add X", "should set up Y" — these are tasks, not knowledge
- Procedural steps: "ran pip install", "edited the config"
- Troubleshooting and debugging
- Tool outputs and code snippets
- Both sides of the same decision — only the outcome matters
- Inferences not directly stated in the conversation

RULES:
- Each fact must be atomic and concrete (one idea per fact)
- Use "User" for first-person references
- Only state what was explicitly said — do not infer or add context
- Prefer fewer high-quality facts over many low-quality ones
- If nothing durable was discussed, return an empty list

CONVERSATION:
{conversation}"""


class ChatExtractionSchema(BaseModel):
    facts: list[str] = []


def _format_messages(messages: tuple[dict, ...]) -> str:
    parts = []
    for msg in messages:
        role = msg["role"]
        if role == "tool":
            continue
        content = msg["content"]
        if not content or not isinstance(content, str):
            continue
        if content.startswith("[Session State Handoff]"):
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

    prompt = CHAT_EXTRACTION_PROMPT.format(conversation=conversation)

    try:
        client = get_completion_client(model)
        response = await client.completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
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


def make_chat_extraction_handler(
    get_memory: Callable[[], FactMemory | None],
    get_model: Callable[[], str],
) -> Handler[ContextCompressed]:
    async def handle(event: ContextCompressed) -> None:
        memory = get_memory()
        if not memory:
            return

        facts = await extract_from_chat(event.messages, get_model())
        if not facts:
            return

        _logger.info("Extracted %d facts from compressed context", len(facts))
        for fact_text in facts:
            await memory.remember(
                text=fact_text,
                source_type="chat",
                source_ref=event.session_id,
            )

    return handle
