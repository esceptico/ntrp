_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "is", "are", "was", "were",
    "in", "on", "at", "to", "for", "of", "with", "by", "from",
    "it", "its", "this", "that", "these", "those",
    "i", "me", "my", "we", "our", "you", "your",
    "he", "she", "his", "her", "they", "them", "their",
    "do", "does", "did", "has", "have", "had",
    "be", "been", "being", "will", "would", "could", "should",
    "not", "no", "so", "if", "how", "what", "when", "where", "who", "which",
})


def build_fts_query(query: str) -> str | None:
    """Build FTS5 query: OR between meaningful terms, stopwords filtered.

    Returns None if no meaningful terms remain.
    """
    terms = query.split()
    meaningful = [t for t in terms if t.lower() not in _STOPWORDS and len(t) > 1]
    if not meaningful:
        meaningful = [t for t in terms if len(t) > 1]
    if not meaningful:
        return None
    quoted = [f'"{t.replace(chr(34), chr(34) + chr(34))}"' for t in meaningful]
    return " OR ".join(quoted)
