from __future__ import annotations

import json
import re
import string
from dataclasses import dataclass, field
from typing import Literal, Protocol

from pydantic import BaseModel, Field, field_validator

from ntrp.knowledge.entities import extract_entity_graph
from ntrp.logging import get_logger

_logger = get_logger(__name__)

EntityResolutionState = Literal["resolved", "ambiguous", "unresolved", "ignored"]

_GENERIC_ENTITY_NAMES = {
    "agent",
    "agents",
    "alert",
    "alerts",
    "app",
    "apps",
    "bug",
    "bugs",
    "chat",
    "code",
    "data",
    "database",
    "db",
    "deploy",
    "docs",
    "email",
    "event",
    "events",
    "fact",
    "facts",
    "feature",
    "file",
    "files",
    "issue",
    "issues",
    "job",
    "jobs",
    "memory",
    "message",
    "messages",
    "model",
    "models",
    "note",
    "notes",
    "project",
    "projects",
    "repo",
    "repos",
    "run",
    "runs",
    "service",
    "services",
    "session",
    "sessions",
    "system",
    "task",
    "tasks",
    "test",
    "tests",
    "tool",
    "tools",
    "user",
    "workflow",
}

_ALLOWED_ENTITY_TYPES = {
    "person",
    "organization",
    "team",
    "project",
    "product",
    "repository",
    "service",
    "system",
    "model",
    "api",
    "file",
    "document",
    "location",
    "event",
    "concept",
    "account",
    "other",
}

_EXTRACTOR_OWNED_KEY = "extractor_owned_entities"
_ALIAS_KEY = "aliases"


class EntityMentionProposal(BaseModel):
    surface: str = Field(description="Exact mention text copied from the source when possible")
    canonical_name: str | None = Field(default=None, description="Stable canonical entity name, not a sentence")
    entity_type: str = Field(default="other", description="Small semantic type such as person, project, service, repository")
    aliases: list[str] = Field(default_factory=list, description="Known aliases/acronyms/spellings for the same entity")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    resolution: EntityResolutionState = Field(default="resolved")
    ambiguity_candidates: list[str] = Field(default_factory=list)
    evidence_quote: str | None = None

    @field_validator("surface", "canonical_name", mode="before")
    @classmethod
    def _stringify(cls, value: object) -> str | None:
        if value is None:
            return None
        return str(value)

    @field_validator("entity_type")
    @classmethod
    def _normalize_type(cls, value: str) -> str:
        normalized = re.sub(r"[^a-z0-9_]+", "_", value.casefold()).strip("_") or "other"
        return normalized if normalized in _ALLOWED_ENTITY_TYPES else "other"


class EntityRelationProposal(BaseModel):
    source: str
    relation: str
    target: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_quote: str | None = None


class EntityExtractionProposal(BaseModel):
    entities: list[EntityMentionProposal] = Field(default_factory=list)
    relations: list[EntityRelationProposal] = Field(default_factory=list)
    notes: str | None = None


@dataclass(frozen=True)
class ResolvedEntity:
    name: str
    entity_type: str = "other"
    aliases: tuple[str, ...] = ()
    confidence: float = 0.0
    mentions: tuple[str, ...] = ()


@dataclass(frozen=True)
class EntityResolutionResult:
    entities: tuple[ResolvedEntity, ...] = ()
    edges: tuple[dict[str, str], ...] = ()
    rejected: tuple[dict[str, object], ...] = ()
    unresolved: tuple[dict[str, object], ...] = ()
    extractor: str = "knowledge.entities.resolver.v1"

    @property
    def names(self) -> list[str]:
        return [entity.name for entity in self.entities]

    @property
    def alias_map(self) -> dict[str, list[str]]:
        return {entity.name: list(entity.aliases) for entity in self.entities if entity.aliases}

    @property
    def type_map(self) -> dict[str, str]:
        return {entity.name: entity.entity_type for entity in self.entities if entity.entity_type != "other"}


class EntityExtractor(Protocol):
    name: str

    async def extract(self, title: str, text: str, *, source_ids: list[str]) -> EntityExtractionProposal: ...


@dataclass
class HeuristicEntityExtractor:
    """Offline fallback extractor.

    This is intentionally a fallback only: real runtime extraction should prefer
    `ModelEntityExtractor`, while tests/local maintenance can still run without
    provider credentials.
    """

    name: str = "knowledge.entities.heuristic.v2"

    async def extract(self, title: str, text: str, *, source_ids: list[str]) -> EntityExtractionProposal:
        graph = extract_entity_graph(title, text, source_ids=source_ids)
        entities = [
            EntityMentionProposal(
                surface=name,
                canonical_name=name,
                aliases=graph.aliases.get(name, []),
                confidence=0.62,
                resolution="resolved",
            )
            for name in graph.entities
        ]
        relations = [
            EntityRelationProposal(
                source=edge["source"],
                relation=edge["relation"],
                target=edge["target"],
                confidence=0.55,
            )
            for edge in graph.edges
            if {"source", "relation", "target"} <= set(edge)
        ]
        return EntityExtractionProposal(entities=entities, relations=relations)


@dataclass
class ModelEntityExtractor:
    model: str
    name: str = "knowledge.entities.model.v1"
    max_tokens: int = 1800

    async def extract(self, title: str, text: str, *, source_ids: list[str]) -> EntityExtractionProposal:
        from ntrp.llm.router import get_completion_client

        client = get_completion_client(self.model)
        response = await client.completion(
            model=self.model,
            temperature=0,
            max_tokens=self.max_tokens,
            response_format=EntityExtractionProposal,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Extract durable named entities from a personal-assistant memory object. "
                        "Return JSON matching the schema. Prefer concrete entities: people, companies, teams, projects, "
                        "repos, services, products, APIs, models, files, documents, accounts, events, and specific concepts. "
                        "Do not emit generic nouns like 'task', 'tool', 'system', or 'message' unless they are part of a proper name. "
                        "Use canonical names for the user's real-world entity, include aliases/acronyms/spellings, and mark ambiguous "
                        "or weak guesses as ambiguous/unresolved instead of forcing a merge. Copy evidence quotes from the input when possible."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"title": title, "text": text, "source_ids": source_ids}, ensure_ascii=False
                    ),
                },
            ],
        )
        content = response.choices[0].message.content if response.choices else None
        if not content:
            return EntityExtractionProposal()
        return EntityExtractionProposal.model_validate_json(content)


@dataclass
class _EntityAccumulator:
    name: str
    entity_type: str = "other"
    aliases: list[str] = field(default_factory=list)
    confidence: float = 0.0
    mentions: list[str] = field(default_factory=list)


def canonical_key(value: str) -> str:
    value = value.casefold().replace("&", " and ")
    value = value.translate(str.maketrans("", "", string.punctuation.replace(".", "")))
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _compact_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", canonical_key(value))


def _looks_like_identifier_or_metric(value: str, key: str) -> bool:
    lowered = value.casefold()
    if re.match(r"^(knowledge|session|run|turn):", lowered):
        return True
    if re.fullmatch(r"[0-9_:-]+", lowered):
        return True
    if re.fullmatch(r"\d+\s+(runs?|run details|artifacts?|cursor pages?|timeouts?|messages?)", key):
        return True
    if re.search(r"\d{1,2}:\d{2}:\d{2}.*\bwindow\b", lowered):
        return True
    letters = sum(1 for char in value if char.isalpha())
    digits = sum(1 for char in value if char.isdigit())
    return digits >= 6 and letters <= 4


def _clean_name(value: str | None) -> str | None:
    if value is None:
        return None
    value = re.sub(r"\s+", " ", value.strip(" \t\n\r.,;:()[]{}<>\"'`"))
    if len(value) < 2 or len(value) > 120:
        return None
    key = canonical_key(value)
    if not key or key in _GENERIC_ENTITY_NAMES or _looks_like_identifier_or_metric(value, key):
        return None
    return value


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _clean_name(value)
        if not cleaned:
            continue
        key = _compact_key(cleaned)
        if key and key not in seen:
            seen.add(key)
            out.append(cleaned)
    return out


def _source_id_entities(source_ids: list[str]) -> list[EntityMentionProposal]:
    proposals: list[EntityMentionProposal] = []
    for source_id in source_ids:
        if ":" not in source_id:
            continue
        prefix, raw = source_id.split(":", 1)
        if prefix not in {"project", "repo", "entity", "user", "team", "app", "service", "model", "account"}:
            continue
        cleaned = _clean_name(raw.replace("-", " ").replace("_", " "))
        if cleaned:
            proposals.append(
                EntityMentionProposal(
                    surface=raw,
                    canonical_name=cleaned,
                    entity_type="repository" if prefix == "repo" else prefix,
                    aliases=[raw],
                    confidence=0.9,
                    resolution="resolved",
                )
            )
    return proposals


def resolve_entity_proposal(
    proposal: EntityExtractionProposal,
    *,
    source_ids: list[str],
    extractor_name: str,
    min_confidence: float = 0.5,
) -> EntityResolutionResult:
    accumulators: dict[str, _EntityAccumulator] = {}
    alias_to_key: dict[str, str] = {}
    rejected: list[dict[str, object]] = []
    unresolved: list[dict[str, object]] = []

    for mention in [*proposal.entities, *_source_id_entities(source_ids)]:
        display_name = _clean_name(mention.canonical_name) or _clean_name(mention.surface)
        if mention.resolution in {"ambiguous", "unresolved"}:
            unresolved.append(
                {
                    "surface": mention.surface,
                    "canonical_name": mention.canonical_name,
                    "resolution": mention.resolution,
                    "candidates": mention.ambiguity_candidates,
                    "confidence": mention.confidence,
                }
            )
            continue
        if mention.resolution == "ignored" or mention.confidence < min_confidence or not display_name:
            rejected.append(
                {
                    "surface": mention.surface,
                    "canonical_name": mention.canonical_name,
                    "resolution": mention.resolution,
                    "confidence": mention.confidence,
                    "reason": "low_confidence_or_invalid",
                }
            )
            continue

        keys = [_compact_key(display_name), *[_compact_key(alias) for alias in mention.aliases], _compact_key(mention.surface)]
        keys = [key for key in keys if key]
        existing_key = next((alias_to_key[key] for key in keys if key in alias_to_key), None)
        entity_key = existing_key or keys[0]

        if entity_key not in accumulators:
            accumulators[entity_key] = _EntityAccumulator(name=display_name, entity_type=mention.entity_type)
        acc = accumulators[entity_key]
        if acc.entity_type == "other" and mention.entity_type != "other":
            acc.entity_type = mention.entity_type
        acc.confidence = max(acc.confidence, mention.confidence)
        acc.mentions = _dedupe([*acc.mentions, mention.surface, display_name])
        acc.aliases = _dedupe([*acc.aliases, mention.surface, *mention.aliases])
        acc.aliases = [alias for alias in acc.aliases if _compact_key(alias) != _compact_key(acc.name)]
        for key in keys:
            alias_to_key[key] = entity_key

    name_by_key = {key: acc.name for key, acc in accumulators.items()}
    edges: list[dict[str, str]] = []
    for relation in proposal.relations:
        if relation.confidence < min_confidence:
            continue
        src_key = alias_to_key.get(_compact_key(relation.source))
        dst_key = alias_to_key.get(_compact_key(relation.target))
        if not src_key or not dst_key or src_key == dst_key:
            continue
        relation_name = re.sub(r"[^a-z0-9_]+", "_", relation.relation.casefold()).strip("_") or "related_to"
        edges.append({"source": name_by_key[src_key], "relation": relation_name, "target": name_by_key[dst_key]})

    entities = tuple(
        ResolvedEntity(
            name=acc.name,
            entity_type=acc.entity_type,
            aliases=tuple(acc.aliases[:16]),
            confidence=acc.confidence,
            mentions=tuple(acc.mentions[:16]),
        )
        for acc in sorted(accumulators.values(), key=lambda item: item.name.casefold())[:32]
    )
    unique_edges = tuple(dict(item) for item in {json.dumps(edge, sort_keys=True): edge for edge in edges[:64]}.values())
    return EntityResolutionResult(
        entities=entities,
        edges=unique_edges,
        rejected=tuple(rejected),
        unresolved=tuple(unresolved),
        extractor=f"{extractor_name}+knowledge.entities.resolver.v1",
    )


def merge_resolved_entity_metadata(metadata: dict[str, object], result: EntityResolutionResult) -> dict[str, object]:
    merged = dict(metadata)
    graph = merged.get("entity_graph") if isinstance(merged.get("entity_graph"), dict) else {}
    previous_extractor_owned = set(
        str(item)
        for item in graph.get(_EXTRACTOR_OWNED_KEY, [])
        if isinstance(graph, dict) and isinstance(graph.get(_EXTRACTOR_OWNED_KEY), list)
    )
    existing_entities = [str(item) for item in merged.get("entities", [])] if isinstance(merged.get("entities"), list) else []
    preserved = [entity for entity in existing_entities if entity not in previous_extractor_owned]
    entity_names = _dedupe([*preserved, *result.names])

    existing_aliases = graph.get(_ALIAS_KEY, {}) if isinstance(graph, dict) and isinstance(graph.get(_ALIAS_KEY), dict) else {}
    aliases: dict[str, list[str]] = {
        str(name): [str(alias) for alias in values]
        for name, values in existing_aliases.items()
        if isinstance(values, list) and str(name) in preserved
    }
    aliases.update(result.alias_map)

    merged["entities"] = entity_names
    merged["entity_graph"] = {
        "entities": entity_names,
        "aliases": aliases,
        "entity_types": result.type_map,
        "edges": list(result.edges),
        "unresolved": list(result.unresolved),
        "rejected": list(result.rejected),
        _EXTRACTOR_OWNED_KEY: result.names,
        "extractor": result.extractor,
    }
    return merged


@dataclass
class EntityExtractionPipeline:
    primary: EntityExtractor | None = None
    fallback: EntityExtractor = field(default_factory=HeuristicEntityExtractor)

    async def extract(self, title: str, text: str, *, source_ids: list[str]) -> EntityResolutionResult:
        if self.primary is not None:
            try:
                proposal = await self.primary.extract(title, text, source_ids=source_ids)
                return resolve_entity_proposal(proposal, source_ids=source_ids, extractor_name=self.primary.name)
            except Exception:
                _logger.warning("Primary entity extractor failed; falling back to heuristic extractor", exc_info=True)

        proposal = await self.fallback.extract(title, text, source_ids=source_ids)
        return resolve_entity_proposal(proposal, source_ids=source_ids, extractor_name=self.fallback.name)

    async def merge_metadata(
        self, metadata: dict[str, object], title: str, text: str, source_ids: list[str]
    ) -> dict[str, object]:
        result = await self.extract(title, text, source_ids=source_ids)
        return merge_resolved_entity_metadata(metadata, result)
