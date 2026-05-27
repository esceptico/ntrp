from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from ntrp.knowledge.entity_extraction import EntityResolutionResult
from ntrp.knowledge.models import (
    KnowledgeObject,
    KnowledgeObjectCreate,
    KnowledgeObjectStatus,
    KnowledgeObjectType,
    KnowledgeObjectUpdate,
)
from ntrp.knowledge.store import KnowledgeObjectRepository
from ntrp.logging import get_logger
from ntrp.memory.facts import FactMemory

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

_logger = get_logger(__name__)

PROFILE_SCHEMA_VERSION = "trimem.profile.v1"
PROFILE_POLICY_VERSION = "knowledge.profiles.trimem.v1"
PROFILE_ENTITY_EXTRACTOR = "knowledge.entities.profile_metadata.v1"
PROFILE_EVIDENCE_TYPES = {
    KnowledgeObjectType.FACT,
    KnowledgeObjectType.LESSON,
    KnowledgeObjectType.PROCEDURE,
}
PROFILE_AUTO_STOP_NAMES = {
    "audit",
    "audits",
    "profile",
    "profiles",
    "run",
    "runs",
    "session",
    "sessions",
    "task",
    "tasks",
    "user",
}
PROFILE_AUTO_TOPIC_TERMS = {
    "audit",
    "audits",
    "case",
    "cases",
    "check",
    "checks",
    "context",
    "issue",
    "issues",
    "note",
    "notes",
    "report",
    "reports",
    "summary",
    "topic",
    "topics",
}
PROFILE_FILE_SUFFIX_RE = re.compile(r"\.(css|html|jsx?|json|md|markdown|py|sh|sql|tsx?|txt|ya?ml)$", re.IGNORECASE)


class EntityProfileSynthesis(BaseModel):
    summary: str = Field(default="")
    identity: str = Field(default="")
    role_context: str = Field(default="")
    personality: str = Field(default="")
    interests: str = Field(default="")
    career: str = Field(default="")
    values: str = Field(default="")
    relationships: str = Field(default="")
    life_events: str = Field(default="")
    preferences: str = Field(default="")
    behavioral_tendencies: str = Field(default="")
    open_questions: str = Field(default="")
    caveats: str = Field(default="Derived synthesis. Source objects/raw episodes remain canonical.")


@dataclass(frozen=True)
class ProfileSynthesisOutput:
    text: str
    sections: list[dict[str, object]]
    synthesis_mode: str


def unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


def profile_entity_resolution(object_type: KnowledgeObjectType, metadata: dict[str, Any]) -> EntityResolutionResult | None:
    if object_type != KnowledgeObjectType.ENTITY_PROFILE:
        return None
    raw_entities = metadata.get("entities")
    if not isinstance(raw_entities, list) or not any(str(item).strip() for item in raw_entities):
        return None
    return EntityResolutionResult(extractor=PROFILE_ENTITY_EXTRACTOR)


def auto_profile_entity_like(name: str) -> bool:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9.+-]*", name)
    if not tokens or len(tokens) > 8:
        return False
    lowered_tokens = {token.casefold() for token in tokens}
    if lowered_tokens & PROFILE_AUTO_TOPIC_TERMS:
        return False

    def token_has_proper_signal(token: str) -> bool:
        return token[:1].isupper() or token.isupper() or any(char.isupper() for char in token[1:])

    return all(token_has_proper_signal(token) for token in tokens)


def profile_entity_name(value: str, *, explicit: bool) -> str | None:
    name = re.sub(r"\s+", " ", value.strip(" \t\n\r.,;:()[]{}<>\"'`"))
    if len(name) < 2 or len(name) > 120:
        return None
    lowered = name.casefold()
    if "/" in name or "\\" in name or "_" in name or PROFILE_FILE_SUFFIX_RE.search(lowered):
        return None
    if re.fullmatch(r"[0-9_:-]+", lowered):
        return None
    if re.search(r"\b[a-z][A-Za-z0-9]*[A-Z][A-Za-z0-9]*\b", name):
        return None
    if re.match(r"^(knowledge|session|run|turn):", lowered):
        return None
    if not explicit:
        if lowered in PROFILE_AUTO_STOP_NAMES:
            return None
        if not auto_profile_entity_like(name):
            return None
    return name


def evidence_source_ids(evidence: list[KnowledgeObject]) -> list[str]:
    return unique([f"knowledge:{obj.id}" for obj in evidence] + [sid for obj in evidence for sid in obj.source_ids])


def source_object_ids(evidence: list[KnowledgeObject]) -> list[int]:
    return [obj.id for obj in evidence]


def profile_candidate_names(obj: KnowledgeObject, *, explicit: bool = False) -> list[str]:
    raw_names: list[str] = []
    raw = obj.metadata.get("entities")
    if isinstance(raw, list):
        raw_names.extend(str(item) for item in raw if str(item).strip())
    graph = obj.metadata.get("entity_graph")
    if isinstance(graph, dict) and isinstance(graph.get("entities"), list):
        raw_names.extend(str(item) for item in graph["entities"] if str(item).strip())
    return unique([name for raw_name in raw_names if (name := profile_entity_name(raw_name, explicit=explicit)) is not None])


def should_progressively_update_profiles(obj: KnowledgeObject) -> bool:
    return (
        obj.object_type in PROFILE_EVIDENCE_TYPES
        and obj.status.value in {"active", "approved"}
        and bool(obj.source_ids)
        and obj.metadata.get("profile_update_disabled") is not True
    )


def _profile_sections_from_synthesis(synthesis: EntityProfileSynthesis, evidence: list[KnowledgeObject]) -> list[dict[str, object]]:
    refs = source_object_ids(evidence)
    sources = evidence_source_ids(evidence)
    sections: list[dict[str, object]] = []
    for key, label in (
        ("summary", "summary"),
        ("identity", "identity"),
        ("role_context", "role_context"),
        ("personality", "personality"),
        ("interests", "interests"),
        ("career", "career"),
        ("values", "values"),
        ("relationships", "relationships"),
        ("life_events", "life_events"),
        ("preferences", "preferences"),
        ("behavioral_tendencies", "behavioral_tendencies"),
        ("open_questions", "open_questions"),
        ("caveats", "caveats"),
    ):
        value = getattr(synthesis, key).strip()
        if value:
            sections.append({"name": label, "summary": value, "source_object_ids": refs, "source_ids": sources})
    return sections


def _profile_text(entity_name: str, synthesis: EntityProfileSynthesis) -> str:
    lines = [
        f"# Entity profile: {entity_name}",
        "",
        "Derived profile. Canonical truth stays in cited source objects/raw episodes.",
    ]
    section_labels = (
        ("summary", "Summary"),
        ("identity", "Identity"),
        ("role_context", "Role / Context"),
        ("personality", "Personality"),
        ("interests", "Interests"),
        ("career", "Career"),
        ("values", "Values"),
        ("relationships", "Relationships"),
        ("life_events", "Life Events"),
        ("preferences", "Preferences"),
        ("behavioral_tendencies", "Behavioral Tendencies"),
        ("open_questions", "Open Questions"),
        ("caveats", "Caveats"),
    )
    for key, label in section_labels:
        value = getattr(synthesis, key).strip()
        if value:
            lines.extend(["", f"## {label}", value])
    return "\n".join(lines).strip()


def _evidence_payload(evidence: list[KnowledgeObject]) -> list[dict[str, Any]]:
    return [
        {
            "id": obj.id,
            "type": obj.object_type.value,
            "title": obj.title,
            "text": obj.text,
            "source_ids": obj.source_ids,
            "metadata": {
                key: value
                for key, value in obj.metadata.items()
                if key in {"kind", "happened_at", "valid_as_of", "source_quote", "confidence", "entities"}
            },
        }
        for obj in evidence
    ]


class KnowledgeProfileSynthesizer:
    def __init__(self, *, model: str | None = None):
        self.model = model

    async def synthesize(
        self,
        *,
        entity_name: str,
        evidence: list[KnowledgeObject],
        existing_profile: KnowledgeObject | None = None,
    ) -> ProfileSynthesisOutput:
        if self.model:
            synthesis = await self._llm_synthesize(entity_name=entity_name, evidence=evidence, existing_profile=existing_profile)
            return ProfileSynthesisOutput(
                text=_profile_text(entity_name, synthesis),
                sections=_profile_sections_from_synthesis(synthesis, evidence),
                synthesis_mode="llm",
            )
        synthesis = self._fallback_synthesis(entity_name, evidence, existing_profile)
        return ProfileSynthesisOutput(
            text=_profile_text(entity_name, synthesis),
            sections=_profile_sections_from_synthesis(synthesis, evidence),
            synthesis_mode="deterministic_fallback",
        )

    async def _llm_synthesize(
        self,
        *,
        entity_name: str,
        evidence: list[KnowledgeObject],
        existing_profile: KnowledgeObject | None,
    ) -> EntityProfileSynthesis:
        from ntrp.llm.router import get_completion_client

        payload = {
            "entity_name": entity_name,
            "current_profile": existing_profile.text if existing_profile is not None else None,
            "new_facts_or_patterns": _evidence_payload(evidence),
        }
        response = await get_completion_client(self.model).completion(
            model=self.model,
            temperature=0.2,
            max_tokens=1200,
            response_format=EntityProfileSynthesis,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You update progressive TriMem-style persona/entity profiles. "
                        "Input is an existing profile plus newly extracted source-backed facts/patterns. "
                        "Return a compact structured synthesis about the named entity only. "
                        "Preserve existing information unless contradicted. Update only what the new evidence supports. "
                        "Do not concatenate facts, do not repeat titles, and do not summarize reported bugs/products unless they reveal the entity's role, responsibilities, preferences, relationships, values, or behavior. "
                        "Keep each populated section 1-3 concise lines. Leave unsupported sections empty."
                    ),
                },
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
        )
        content = response.choices[0].message.content if response.choices else None
        if not content:
            return self._fallback_synthesis(entity_name, evidence, existing_profile)
        try:
            return EntityProfileSynthesis.model_validate_json(content)
        except Exception:
            try:
                return EntityProfileSynthesis.model_validate(json.loads(content))
            except Exception:
                return self._fallback_synthesis(entity_name, evidence, existing_profile)

    def _fallback_synthesis(
        self,
        entity_name: str,
        evidence: list[KnowledgeObject],
        existing_profile: KnowledgeObject | None,
    ) -> EntityProfileSynthesis:
        existing_summary = ""
        if existing_profile is not None:
            for line in existing_profile.text.splitlines():
                if line.strip() and not line.startswith("#") and "Derived profile" not in line:
                    existing_summary = line.strip()
                    break
        kinds = ", ".join(sorted({obj.object_type.value for obj in evidence})) or "source-backed memories"
        refs = ", ".join(f"knowledge:{obj.id}" for obj in evidence[:8])
        return EntityProfileSynthesis(
            summary=existing_summary or f"{entity_name} appears in {len(evidence)} source-backed {kinds} relevant to long-term memory.",
            role_context=f"Latest update is grounded in {refs}. Use cited source objects/raw episodes for exact details.",
            caveats="Deterministic fallback profile because no memory LLM model was configured; refresh with an LLM-backed model for deeper synthesis.",
        )


class KnowledgeProfileService:
    def __init__(
        self,
        *,
        repo: KnowledgeObjectRepository,
        memory: FactMemory,
        synthesizer: KnowledgeProfileSynthesizer,
        sync_entity_resolution: Callable[[KnowledgeObject, EntityResolutionResult], Awaitable[None]],
        embed_object: Callable[[KnowledgeObject], Awaitable[None]],
        emit_event: Callable[[KnowledgeObject, str], Awaitable[None]],
    ):
        self._repo = repo
        self._memory = memory
        self._synthesizer = synthesizer
        self._sync_entity_resolution = sync_entity_resolution
        self._embed_object = embed_object
        self._emit_event = emit_event

    async def upsert(
        self,
        entity_name: str,
        evidence: list[KnowledgeObject],
        *,
        explicit_refresh: bool = False,
    ) -> KnowledgeObject | None:
        evidence = [obj for obj in evidence if obj.object_type in PROFILE_EVIDENCE_TYPES and obj.source_ids]
        if not evidence:
            return None
        existing = await self._repo.get_entity_profile(entity_name)
        if existing is not None and existing.metadata.get("profile_schema_version") != PROFILE_SCHEMA_VERSION:
            await self._repo.update(
                existing.id,
                KnowledgeObjectUpdate(
                    status=KnowledgeObjectStatus.ARCHIVED,
                    metadata={
                        **existing.metadata,
                        "archived_reason": "replaced_legacy_rollup_profile",
                        "archived_by": PROFILE_POLICY_VERSION,
                    },
                ),
            )
            existing = None
        try:
            synthesis = await self._synthesizer.synthesize(
                entity_name=entity_name,
                evidence=evidence,
                existing_profile=existing,
            )
        except Exception:
            _logger.warning("Failed to synthesize profile for %s", entity_name, exc_info=True)
            return existing

        now = datetime.now(UTC).isoformat()
        existing_source_object_ids = []
        if existing is not None and isinstance(existing.metadata.get("source_object_ids"), list):
            existing_source_object_ids = [int(item) for item in existing.metadata["source_object_ids"] if str(item).isdigit()]
        source_object_id_list = unique([*(str(item) for item in existing_source_object_ids), *(str(item) for item in source_object_ids(evidence))])
        source_object_id_ints = [int(item) for item in source_object_id_list]
        source_ids = unique([*(existing.source_ids if existing is not None else []), *evidence_source_ids(evidence)])
        metadata = {
            **(existing.metadata if existing is not None else {}),
            "processor": "profile_synthesis",
            "profile_schema_version": PROFILE_SCHEMA_VERSION,
            "policy_version": PROFILE_POLICY_VERSION,
            "memory_tier": "profile",
            "profile_entity": entity_name,
            "entities": [entity_name],
            "source_object_ids": source_object_id_ints,
            "last_updated_from_object_ids": source_object_ids(evidence),
            "profile_sections": synthesis.sections,
            "updated_progressively": True,
            "generated_at": (existing.metadata.get("generated_at") if existing is not None else now),
            "valid_as_of": now,
            "stale_after_days": 30,
            "caveats": [
                "Derived synthesis, not canonical truth.",
                "Check cited source objects/raw episodes for exact wording, contradictions, and stale state.",
            ],
            "source_anchored": True,
            "synthesis_mode": synthesis.synthesis_mode,
            "profile_update_count": int(existing.metadata.get("profile_update_count", 0)) + 1 if existing is not None else 1,
            "manual_refresh": explicit_refresh,
        }
        if existing is not None:
            profile = await self._repo.update(
                existing.id,
                KnowledgeObjectUpdate(
                    title=f"Profile: {entity_name}",
                    text=synthesis.text,
                    status=KnowledgeObjectStatus.ACTIVE,
                    activation="prompt",
                    proactiveness_level="L0",
                    score=max(existing.score, 0.6),
                    source_ids=source_ids,
                    metadata=metadata,
                ),
            )
            action = "updated"
        else:
            profile = await self._repo.create(
                KnowledgeObjectCreate(
                    object_type=KnowledgeObjectType.ENTITY_PROFILE,
                    title=f"Profile: {entity_name}",
                    text=synthesis.text,
                    status=KnowledgeObjectStatus.ACTIVE,
                    activation="prompt",
                    proactiveness_level="L0",
                    score=0.6,
                    source_ids=source_ids,
                    metadata=metadata,
                )
            )
            action = "created"
        await self._sync_entity_resolution(profile, EntityResolutionResult(extractor=PROFILE_ENTITY_EXTRACTOR))
        await self._embed_object(profile)
        await self._memory.events.create(
            actor="system",
            action=f"knowledge.profile.{action}",
            target_type=profile.object_type.value,
            target_id=profile.id,
            reason="progressive profile synthesis" if not explicit_refresh else "manual profile refresh",
            policy_version=PROFILE_POLICY_VERSION,
            details={"profile_entity": entity_name, "source_object_ids": source_object_ids(evidence)},
        )
        await self._emit_event(profile, action)
        return profile

    async def refresh(
        self,
        entity_name: str,
        *,
        evidence_limit: int = 12,
        explicit_refresh: bool = True,
    ) -> KnowledgeObject | None:
        # Slice 3 removes the knowledge-object search path this profile refresh
        # depended on. Profile synthesis stays disabled until a memory_items
        # evidence adapter is designed in a later slice.
        _ = (entity_name, evidence_limit, explicit_refresh)
        return None
