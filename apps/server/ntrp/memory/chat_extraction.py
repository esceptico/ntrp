from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from ntrp.agent import Role
from ntrp.constants import CONSOLIDATION_TEMPERATURE, SESSION_HANDOFF_MARKER
from ntrp.core.prompts import env
from ntrp.llm.router import get_completion_client
from ntrp.logging import get_logger
from ntrp.memory.models import FactKind, FactLifetime

_logger = get_logger(__name__)

CHAT_EXTRACTION_PROMPT = env.from_string("""Extract source-of-truth memory facts from this conversation.

Return typed source-of-truth records that are useful to recall later.
Do not write observations, patterns, summaries, or inferred profile statements. Those are derived later from facts.
{% if policy_context %}

APPROVED MEMORY POLICY NOTES
These are user-applied memory policy notes. Use them when directly relevant, but do not let them override the evidence rules.

{{ policy_context }}
{% endif %}

Evidence rules:
- User messages are the evidence source.
- Assistant messages are context only; never turn assistant wording into memory unless a later user message explicitly confirms it.
- User corrections override earlier assistant claims and earlier extracted-looking context.
- Do not store meta-commentary about the current task unless it is a reusable preference, standing rule, or durable decision.

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
- Praise, jokes, reactions, and one-off opinions about the assistant's current output

RULES:
- Each fact must be atomic and concrete (one idea per fact)
- Use "User" for first-person references
- Only state what was explicitly said — do not infer or add context
- Prefer fewer high-quality facts over many low-quality ones
- Keep enough names, dates, project names, and constraints for provenance
- Assign exactly one kind: identity, preference, relationship, decision, project, event, artifact, procedure, constraint, or note
- Assign exactly one lifetime: durable or temporary
- Use salience 0 for normal, 1 for useful, 2 only for durable always-relevant facts
- Use confidence below 1.0 only when the conversation states the fact ambiguously
- Temporary facts must include expires_at; otherwise skip them
- Durable facts must not include expires_at
- Include concrete entity names used by the fact, including User when the fact is about the user
- If nothing useful to remember was discussed, return an empty list

CONVERSATION:
{{ conversation }}""")


class ExtractedChatFact(BaseModel):
    text: str
    kind: FactKind = FactKind.NOTE
    lifetime: FactLifetime = FactLifetime.DURABLE
    salience: int = Field(default=0, ge=0, le=2)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    happened_at: datetime | None = None
    expires_at: datetime | None = None
    entities: list[str] = Field(default_factory=list)

    @field_validator("text")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("entities")
    @classmethod
    def _strip_entities(cls, value: list[str]) -> list[str]:
        return [name.strip() for name in value if name.strip()]


class ChatExtractionSchema(BaseModel):
    facts: list[ExtractedChatFact] = Field(default_factory=list)


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
        label = "USER (evidence)" if role == "user" else "ASSISTANT (context only)"
        parts.append(f"{label}: {content}")
    return "\n\n".join(parts)


async def extract_from_chat(
    messages: tuple[dict, ...],
    model: str,
    policy_context: str | None = None,
) -> list[ExtractedChatFact]:
    conversation = _format_messages(messages)
    if not conversation.strip():
        return []

    prompt = CHAT_EXTRACTION_PROMPT.render(conversation=conversation, policy_context=policy_context)

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
        return [
            fact
            for fact in parsed.facts
            if fact.text
            and (fact.lifetime != FactLifetime.TEMPORARY or fact.expires_at is not None)
            and (fact.lifetime != FactLifetime.DURABLE or fact.expires_at is None)
        ]

    except Exception:
        _logger.warning("Chat extraction failed", exc_info=True)
        return []
