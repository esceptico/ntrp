from re import findall

_ACTION_TERMS = {
    "artifact",
    "brief",
    "doc",
    "document",
    "draft",
    "note",
    "obsidian",
    "plan",
    "proposal",
    "reminder",
    "task",
    "todo",
    "verify",
}

_MEMORY_SYSTEM_TERMS = {
    "activation",
    "activations",
    "activated",
    "database",
    "db",
    "inject",
    "injected",
    "knowledge",
    "memory",
    "memories",
    "retrieval",
    "retrieved",
    "sources",
    "telemetry",
    "trace",
    "traces",
}

_PROFILE_QUERY_TERMS = {
    "about",
    "background",
    "beliefs",
    "constraints",
    "current",
    "goals",
    "habit",
    "habits",
    "identity",
    "interests",
    "overview",
    "personality",
    "preferences",
    "profile",
    "relationship",
    "relationships",
    "state",
    "style",
    "tendencies",
}

_TEMPORAL_QUERY_TERMS = {"current", "latest", "now", "recent", "today", "updated", "when"}
_EVIDENCE_QUERY_TERMS = {"cite", "evidence", "provenance", "source", "sources", "where", "why"}
_PERSONAL_MEMORY_QUESTION_STARTS = (
    "what ",
    "where ",
    "when ",
    "who ",
    "which ",
    "how long",
    "how much",
    "how many",
    "how old",
    "how often",
    "is my",
    "are my",
    "does my",
    "do my",
)
_PERSONAL_RECALL_PHRASES = (
    "do you remember",
    "remember when",
    "remind me",
    "previous chat",
    "previous conversation",
    "our previous",
    "we discussed",
    "we talked",
    "talked about",
    "last time",
    "earlier",
    "you told me",
    "you recommended",
    "you suggested",
    "you provided",
    "did i",
    "do i have",
    "do i prefer",
    "do i like",
    "have i",
    "was i",
    "am i",
    "did we",
    "do we have",
    "have we",
    "was our",
)
_PERSONALIZED_ASSISTANCE_TERMS = {
    "advice",
    "recommend",
    "recommendation",
    "recommendations",
    "suggest",
    "suggestion",
    "suggestions",
    "tips",
}
_PERSONALIZED_ASSISTANCE_CONTEXT_TERMS = {
    "current",
    "again",
    "interesting",
    "upcoming",
    "tonight",
    "weekend",
    "struggling",
    "thinking",
    "setup",
    "trip",
    "kitchen",
    "recipes",
    "colleagues",
    "activities",
}
_TEMPORAL_MEMORY_TERMS = {"after", "before", "between", "earlier", "first", "later", "passed", "since"}

_SEMANTIC_ALIAS_SETS = (
    (
        {"music", "streaming", "service", "platform", "app"},
        {"spotify", "tidal", "soundcloud", "bandcamp", "pandora", "youtube", "apple"},
        "music streaming services",
    ),
)

_INFORMATIVE_TERM_STOPWORDS = {
    "about",
    "again",
    "amount",
    "been",
    "before",
    "being",
    "could",
    "did",
    "does",
    "doing",
    "for",
    "from",
    "have",
    "having",
    "how",
    "lately",
    "many",
    "much",
    "name",
    "need",
    "please",
    "should",
    "some",
    "that",
    "the",
    "them",
    "there",
    "thing",
    "things",
    "this",
    "using",
    "what",
    "when",
    "where",
    "which",
    "with",
    "would",
}


def query_terms(text: str, *, min_len: int = 3) -> set[str]:
    return {term for term in findall(r"[a-zA-Z0-9_]+", text.lower()) if len(term) >= min_len}


def _term_variants(term: str) -> set[str]:
    variants = {term}
    if len(term) > 4 and term.endswith("ies"):
        variants.add(f"{term[:-3]}y")
    if len(term) > 3 and term.endswith("s") and not term.endswith("ss"):
        variants.add(term[:-1])
    return variants


def informative_terms(text: str, *, min_len: int = 3) -> set[str]:
    terms: set[str] = set()
    for term in query_terms(text, min_len=min_len):
        if term in _INFORMATIVE_TERM_STOPWORDS:
            continue
        terms.update(_term_variants(term))
    return terms


def semantic_alias_terms(query: str) -> tuple[set[str], list[str]]:
    """Return domain aliases for natural-language category queries.

    This is a lightweight bridge for cases where the user asks by category
    (e.g. "music streaming service") but the memory only names an instance
    (e.g. "Spotify"). It intentionally stays small and generic; embeddings
    still remain the right long-term retrieval path.
    """

    terms = query_terms(query, min_len=3)
    aliases: set[str] = set()
    reasons: list[str] = []
    for triggers, values, reason in _SEMANTIC_ALIAS_SETS:
        if {"music", "streaming"}.issubset(terms) and terms & triggers:
            aliases |= values
            reasons.append(reason)
    return aliases, reasons


def semantic_alias_score(query: str, text: str) -> float:
    aliases, _ = semantic_alias_terms(query)
    if not aliases:
        return 0.0
    text_terms = query_terms(text, min_len=3)
    return 1.0 if aliases & text_terms else 0.0


def query_wants_memory_system(query: str) -> bool:
    lowered = query.lower()
    terms = query_terms(query, min_len=2)
    if not ({"activation", "activations", "activated"} & terms):
        return False
    if len(terms) <= 6 and any(phrase in lowered for phrase in ("what", "have", "activations")):
        return True
    return bool(terms & _MEMORY_SYSTEM_TERMS) and any(
        phrase in lowered
        for phrase in (
            "what we have",
            "what do we have",
            "current",
            "database",
            "debug",
            "inspect",
            "memory",
            "retrieval",
            "telemetry",
        )
    )


def query_wants_profile(query: str) -> bool:
    lowered = query.lower()
    terms = query_terms(query, min_len=2)
    if "profile" in terms or "profiles" in terms:
        return True
    return bool(terms & _PROFILE_QUERY_TERMS) and any(
        phrase in lowered
        for phrase in (
            "what do we know",
            "what's the state",
            "what is the state",
            "tell me about",
            "what are my",
            "what does",
            "who is",
        )
    )


def query_wants_temporal_memory(query: str) -> bool:
    lowered = query.lower().strip()
    terms = query_terms(query, min_len=2)
    if not terms & _TEMPORAL_MEMORY_TERMS:
        return False
    if lowered.startswith(("which ", "what ", "when ", "how many days", "how long")):
        return True
    return any(phrase in lowered for phrase in ("days had passed", "happened first", "started first", "came first"))


def query_wants_personal_memory(query: str) -> bool:
    lowered = query.lower().strip()
    terms = query_terms(query, min_len=2)
    personal_terms = {"me", "my", "mine", "we", "our", "ours", "us"}
    has_first_person_i = bool(findall(r"\bi\b", lowered))
    has_personal_pronoun = has_first_person_i or bool(terms & personal_terms)
    has_recall_phrase = any(phrase in lowered for phrase in _PERSONAL_RECALL_PHRASES)
    if has_recall_phrase:
        return True
    if not has_personal_pronoun:
        return False
    if lowered.startswith(("how do i ", "how can i ", "how should i ", "can you help me ")):
        return False
    if lowered.startswith(_PERSONAL_MEMORY_QUESTION_STARTS) and (has_first_person_i or bool(terms & {"my", "mine", "our", "ours"})):
        return True
    if terms & _PERSONALIZED_ASSISTANCE_TERMS and (
        terms & _PERSONALIZED_ASSISTANCE_CONTEXT_TERMS or has_first_person_i or bool(terms & {"my", "mine", "our", "ours"})
    ):
        return True
    return False


def query_wants_action(query: str) -> bool:
    lowered = query.lower()
    return any(term in lowered for term in _ACTION_TERMS)


def query_wants_evidence(query: str) -> bool:
    lowered = query.lower()
    return any(
        term in lowered
        for term in (
            "why",
            "how did",
            "source",
            "sources",
            "evidence",
            "provenance",
            "episode",
            "run",
            "where did",
            "when did",
            "context",
        )
    )


def reformulated_query(query: str) -> tuple[str, list[str]]:
    terms = query_terms(query, min_len=2)
    expansions: list[str] = []
    reasons: list[str] = []
    alias_terms, alias_reasons = semantic_alias_terms(query)
    if alias_terms:
        expansions.append("semantic aliases " + " ".join(sorted(alias_terms)))
        reasons.extend(f"query_reformulation:semantic_alias:{reason}" for reason in alias_reasons)
    if query_wants_profile(query):
        expansions.append("profile identity preferences relationships goals constraints tendencies")
        reasons.append("query_reformulation:profile")
    if terms & _TEMPORAL_QUERY_TERMS:
        expansions.append("current recent updated temporal latest")
        reasons.append("query_reformulation:temporal")
    if query_wants_personal_memory(query):
        expansions.append("personal durable fact preference profile raw memory episode")
        reasons.append("query_reformulation:personal_memory")
    if query_wants_temporal_memory(query):
        expansions.append("temporal event order date sequence raw memory episode")
        reasons.append("query_reformulation:temporal_memory")
    if terms & _EVIDENCE_QUERY_TERMS or query_wants_evidence(query):
        expansions.append("source evidence provenance raw episode")
        reasons.append("query_reformulation:evidence")
    if not expansions:
        return query, []
    return f"{query}\nRetrieval focus: {'; '.join(expansions)}", reasons


def _normalize_activation_terms(terms: set[str]) -> set[str]:
    normalized = set(terms)
    if "activation" in normalized or "activations" in normalized:
        normalized |= {"activation", "activations"}
    return normalized


def lexical_score(query: str, text: str) -> float:
    query_set = _normalize_activation_terms(informative_terms(query))
    if not query_set:
        query_set = _normalize_activation_terms(query_terms(query))
    if not query_set:
        return 0.0
    text_set = _normalize_activation_terms(informative_terms(text))
    if not text_set:
        text_set = _normalize_activation_terms(set(findall(r"[a-zA-Z0-9_]+", text.lower())))
    return len(query_set & text_set) / len(query_set)
