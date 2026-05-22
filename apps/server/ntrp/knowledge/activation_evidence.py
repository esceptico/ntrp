from re import findall

from ntrp.knowledge.activation_query import (
    informative_terms,
    query_terms,
    query_wants_personal_memory,
    query_wants_temporal_memory,
)
from ntrp.knowledge.models import KnowledgeObject, KnowledgeObjectType

_FOCUSED_EVIDENCE_TYPES = {
    KnowledgeObjectType.MEMORY_EPISODE,
    KnowledgeObjectType.EPISODE,
    KnowledgeObjectType.RUN_PROVENANCE,
}
_FOCUSED_EVIDENCE_MAX_CHARS = 2_400


def _sentences_with_offsets(text: str) -> list[tuple[int, str]]:
    rows: list[tuple[int, str]] = []
    offset = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            offset += len(raw_line) + 1
            continue
        parts = [part.strip() for part in findall(r"[^.!?]+[.!?]?", line) if part.strip()] or [line]
        for part in parts:
            rows.append((offset, part))
            offset += len(part) + 1
    return rows


def focused_evidence_text(obj: KnowledgeObject, query: str, *, max_chars: int = _FOCUSED_EVIDENCE_MAX_CHARS) -> tuple[str, bool]:
    if obj.object_type not in _FOCUSED_EVIDENCE_TYPES or len(obj.text) <= max_chars:
        return obj.text, False
    query_set = informative_terms(query, min_len=3) or query_terms(query, min_len=3)
    if not query_set:
        return obj.text[:max_chars], True

    header_lines: list[str] = []
    for line in obj.text.splitlines()[:4]:
        stripped = line.strip()
        if stripped.startswith(("LongMemEval session ", "Date: ", "Session ", "Source ")):
            header_lines.append(stripped)

    sentence_rows = _sentences_with_offsets(obj.text)
    scored: list[tuple[float, int, str]] = []
    temporal_query = query_wants_temporal_memory(query)
    personal_query = query_wants_personal_memory(query)
    for index, sentence in enumerate(sentence for _, sentence in sentence_rows):
        sentence_terms = informative_terms(sentence, min_len=3) or query_terms(sentence, min_len=3)
        if not sentence_terms:
            continue
        overlap = len(query_set & sentence_terms)
        if overlap == 0 and not (temporal_query and any(ch.isdigit() for ch in sentence)):
            continue
        score = float(overlap)
        lowered = sentence.lower()
        if temporal_query and any(ch.isdigit() for ch in sentence):
            score += 0.75
        if personal_query and lowered.startswith(("user:", "assistant:")):
            score += 0.25
        if any(marker in lowered for marker in ("by the way", "recently", "prefer", "recommended", "suggest")):
            score += 0.15
        scored.append((score, index, sentence))

    selected_indexes: set[int] = set()
    for _, index, _ in sorted(scored, reverse=True)[:6]:
        selected_indexes.add(index)
        if index > 0:
            selected_indexes.add(index - 1)
        if index + 1 < len(sentence_rows):
            selected_indexes.add(index + 1)
    selected_sentences = [sentence_rows[index][1] for index in sorted(selected_indexes)]
    if not selected_sentences:
        selected_sentences = [sentence for _, sentence in sentence_rows[:6]]

    parts = [*header_lines, "Focused source snippets:", *selected_sentences]
    focused = "\n".join(dict.fromkeys(part for part in parts if part))
    if len(focused) <= max_chars:
        return focused, True
    return focused[: max_chars - 1].rstrip() + "…", True
