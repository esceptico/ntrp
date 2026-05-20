from __future__ import annotations

from dataclasses import dataclass, field
from re import findall, search

_STOP_ENTITIES = {
    "A",
    "An",
    "And",
    "But",
    "For",
    "From",
    "If",
    "In",
    "It",
    "No",
    "Not",
    "Of",
    "On",
    "Or",
    "The",
    "This",
    "To",
    "Use",
    "When",
    "With",
}

_RELATION_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"(?P<src>[A-Z][\w.-]+(?:\s+[A-Z][\w.-]+){0,3})\s+(?:uses?|runs?|calls?)\s+(?P<dst>[A-Z][\w.-]+(?:\s+[A-Z][\w.-]+){0,3})", "uses"),
    (r"(?P<src>[A-Z][\w.-]+(?:\s+[A-Z][\w.-]+){0,3})\s+(?:prefers?|should use|must use)\s+(?P<dst>[A-Z][\w.-]+(?:\s+[A-Z][\w.-]+){0,3})", "prefers"),
    (r"(?P<src>[A-Z][\w.-]+(?:\s+[A-Z][\w.-]+){0,3})\s+(?:replaces?|supersedes?)\s+(?P<dst>[A-Z][\w.-]+(?:\s+[A-Z][\w.-]+){0,3})", "supersedes"),
    (r"(?P<src>[A-Z][\w.-]+(?:\s+[A-Z][\w.-]+){0,3})\s+(?:contradicts?|invalidates?)\s+(?P<dst>[A-Z][\w.-]+(?:\s+[A-Z][\w.-]+){0,3})", "contradicts"),
)

_TECH_TOKEN_PATTERN = r"\b(?:[a-z]+\.)+[a-z]+\b|\b[A-Za-z][A-Za-z0-9_-]*(?:\.(?:dev|ai|io|com|ts|js|py|json|db))\b"


@dataclass(frozen=True)
class ExtractedEntityGraph:
    entities: list[str] = field(default_factory=list)
    aliases: dict[str, list[str]] = field(default_factory=dict)
    edges: list[dict[str, str]] = field(default_factory=list)

    def to_metadata(self) -> dict[str, object]:
        return {
            "entities": self.entities,
            "aliases": self.aliases,
            "edges": self.edges,
            "extractor": "knowledge.entities.heuristic.v1",
        }


def _clean_entity(raw: str) -> str | None:
    value = " ".join(raw.strip(" .,;:()[]{}<>\n\t").split())
    if len(value) < 3 or value in _STOP_ENTITIES:
        return None
    if value.lower() in {item.lower() for item in _STOP_ENTITIES}:
        return None
    return value


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            out.append(value)
    return out


def _entities_from_source_ids(source_ids: list[str]) -> list[str]:
    entities: list[str] = []
    for source_id in source_ids:
        if ":" not in source_id:
            continue
        prefix, value = source_id.split(":", 1)
        if prefix in {"project", "repo", "entity", "user", "team", "app", "service"}:
            cleaned = _clean_entity(value.replace("-", " ").replace("_", " "))
            if cleaned:
                entities.append(cleaned)
    return entities


def extract_entity_graph(title: str, text: str, *, source_ids: list[str] | None = None) -> ExtractedEntityGraph:
    """Extract a small deterministic entity graph for retrieval.

    This is deliberately local and auditable: capitalized proper-noun phrases,
    domain-ish tech tokens, source-id entities, and simple relation edges. It is
    not pretending to be a full model-mediated entity layer; it gives activation
    a graph-shaped signal without an external dependency.
    """
    source_ids = source_ids or []
    content = f"{title}\n{text}"
    entities: list[str] = []

    for match in findall(r"\b[A-Z][\w.-]+(?:\s+[A-Z][\w.-]+){0,3}\b", content):
        cleaned = _clean_entity(match)
        if cleaned:
            entities.append(cleaned)

    for match in findall(_TECH_TOKEN_PATTERN, content, flags=0):
        cleaned = _clean_entity(match)
        if cleaned:
            entities.append(cleaned)

    entities.extend(_entities_from_source_ids(source_ids))
    entities = _dedupe_preserve_order(entities)[:24]

    aliases: dict[str, list[str]] = {}
    for entity in entities:
        compact = entity.replace(" ", "")
        if compact != entity and len(compact) > 3:
            aliases[entity] = [compact]

    edges: list[dict[str, str]] = []
    for pattern, relation in _RELATION_PATTERNS:
        for matched in findall(pattern, content):
            src, dst = matched
            src_clean = _clean_entity(src)
            dst_clean = _clean_entity(dst)
            if src_clean and dst_clean and src_clean.casefold() != dst_clean.casefold():
                edges.append({"source": src_clean, "relation": relation, "target": dst_clean})

    # Fallback relation for titles like "Dex alert links" -> entity has topic.
    if not edges and len(entities) >= 2 and search(r"\b(prefer|use|uses|should|must|needs?|runs?)\b", content, flags=2):
        edges.append({"source": entities[0], "relation": "related_to", "target": entities[1]})

    return ExtractedEntityGraph(entities=entities, aliases=aliases, edges=edges[:32])


def merge_entity_metadata(metadata: dict[str, object], title: str, text: str, source_ids: list[str]) -> dict[str, object]:
    graph = extract_entity_graph(title, text, source_ids=source_ids)
    if not graph.entities:
        return metadata

    merged = dict(metadata)
    existing_entities = [str(item) for item in merged.get("entities", [])] if isinstance(merged.get("entities"), list) else []
    merged["entities"] = _dedupe_preserve_order([*existing_entities, *graph.entities])

    existing_graph = merged.get("entity_graph") if isinstance(merged.get("entity_graph"), dict) else {}
    existing_edges = existing_graph.get("edges", []) if isinstance(existing_graph, dict) and isinstance(existing_graph.get("edges"), list) else []
    existing_aliases = existing_graph.get("aliases", {}) if isinstance(existing_graph, dict) and isinstance(existing_graph.get("aliases"), dict) else {}
    merged_aliases = {**existing_aliases, **graph.aliases}
    merged["entity_graph"] = {
        "entities": merged["entities"],
        "aliases": merged_aliases,
        "edges": [*existing_edges, *graph.edges],
        "extractor": "knowledge.entities.heuristic.v1",
    }
    return merged
