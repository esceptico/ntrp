import json
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from ntrp.agent import Role
from ntrp.constants import CONSOLIDATION_TEMPERATURE
from ntrp.core.prompts import env
from ntrp.llm.router import get_completion_client
from ntrp.logging import get_logger
from ntrp.memory.models import Fact, FactKind, FactLifetime

_logger = get_logger(__name__)


FACT_KIND_REVIEW_PROMPT = env.from_string("""Classify legacy memory facts for review.

You are not creating, editing, merging, or deleting memory. Return metadata suggestions only.

Kinds:
- identity: stable user identity/background
- preference: stable preference or taste
- relationship: people/org relationships
- decision: chosen outcome, architectural choice, commitment
- project: durable project/product/company context
- event: dated event that may matter later
- artifact: document, URL, file, repo, note, resource
- procedure: reusable how-to or workflow
- constraint: rule, legal/contractual/product constraint
- note: fallback when none of the above is clear

Rules:
- Do not infer beyond the fact text.
- Prefer "note" when uncertain.
- Suggest exactly one lifetime: durable or temporary.
- Use salience 0 for normal, 1 for useful, 2 only for always-relevant durable facts.
- Use confidence below 1.0 when the fact text is ambiguous.
- Temporary suggestions must include expires_at.
- Durable suggestions must not include expires_at.
- Do not suggest supersession here.
- Return one suggestion per input fact id.

Facts:
{{ facts_json }}""")


class FactMetadataSuggestion(BaseModel):
    fact_id: int
    kind: FactKind = FactKind.NOTE
    lifetime: FactLifetime = FactLifetime.DURABLE
    salience: int = Field(default=0, ge=0, le=2)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    expires_at: datetime | None = None
    reason: str = ""

    @field_validator("reason")
    @classmethod
    def _strip_reason(cls, value: str) -> str:
        return value.strip()


class FactMetadataSuggestionSchema(BaseModel):
    suggestions: list[FactMetadataSuggestion] = Field(default_factory=list)


def _fact_review_payload(facts: list[Fact]) -> list[dict]:
    return [
        {
            "id": fact.id,
            "text": fact.text,
            "source_type": fact.source_type,
            "lifetime": fact.lifetime,
            "created_at": fact.created_at.isoformat(),
            "access_count": fact.access_count,
        }
        for fact in facts
    ]


def _normalize_suggestion(suggestion: FactMetadataSuggestion) -> FactMetadataSuggestion:
    if suggestion.lifetime == FactLifetime.TEMPORARY and suggestion.expires_at is None:
        return suggestion.model_copy(
            update={
                "lifetime": FactLifetime.DURABLE,
                "kind": FactKind.NOTE,
                "salience": min(suggestion.salience, 1),
                "reason": f"{suggestion.reason} temporary suggestion had no expiry; kept as note".strip(),
            }
        )
    if suggestion.lifetime == FactLifetime.DURABLE and suggestion.expires_at is not None:
        return suggestion.model_copy(
            update={
                "expires_at": None,
                "reason": f"{suggestion.reason} durable suggestion had expiry; removed expiry".strip(),
            }
        )
    return suggestion


async def suggest_fact_metadata(facts: list[Fact], model: str) -> list[FactMetadataSuggestion]:
    if not facts:
        return []

    fact_ids = {fact.id for fact in facts}
    prompt = FACT_KIND_REVIEW_PROMPT.render(facts_json=json.dumps(_fact_review_payload(facts), ensure_ascii=False))

    try:
        client = get_completion_client(model)
        response = await client.completion(
            model=model,
            messages=[{"role": Role.USER, "content": prompt}],
            response_format=FactMetadataSuggestionSchema,
            temperature=CONSOLIDATION_TEMPERATURE,
        )

        content = response.choices[0].message.content
        if not content:
            return []

        parsed = FactMetadataSuggestionSchema.model_validate_json(content)
        suggestions: list[FactMetadataSuggestion] = []
        seen: set[int] = set()
        for suggestion in parsed.suggestions:
            if suggestion.fact_id not in fact_ids or suggestion.fact_id in seen:
                continue
            seen.add(suggestion.fact_id)
            suggestions.append(_normalize_suggestion(suggestion))
        return suggestions
    except Exception:
        _logger.warning("Fact metadata suggestion failed", exc_info=True)
        return []
