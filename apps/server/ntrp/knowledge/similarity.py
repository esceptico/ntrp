from re import findall

from ntrp.knowledge.models import KnowledgeObject

TOKEN_SYNONYMS = {
    "answers": "answer",
    "responses": "answer",
    "reply": "answer",
    "replies": "answer",
    "brief": "concise",
    "short": "concise",
    "readable": "concise",
    "succinct": "concise",
    "likes": "prefer",
    "like": "prefer",
    "prefers": "prefer",
    "preferred": "prefer",
    "wants": "prefer",
}

STOPWORDS = {
    "the",
    "and",
    "for",
    "that",
    "with",
    "from",
    "this",
    "into",
    "when",
    "then",
    "than",
    "should",
    "would",
    "could",
    "about",
}


def knowledge_tokens_from_text(title: str, text: str) -> set[str]:
    result: set[str] = set()
    for token in findall(r"[a-zA-Z0-9_]+", f"{title} {text}".lower()):
        normalized = TOKEN_SYNONYMS.get(token, token)
        if normalized.endswith("s") and len(normalized) > 4:
            normalized = normalized[:-1]
        if len(normalized) <= 2 or normalized in STOPWORDS:
            continue
        result.add(normalized)
    return result


def knowledge_tokens(obj: KnowledgeObject) -> set[str]:
    return knowledge_tokens_from_text(obj.title, obj.text)


def knowledge_similarity(left: set[str], right: set[str]) -> tuple[float, list[str]]:
    if not left or not right:
        return 0.0, []
    shared = sorted(left & right)
    if not shared:
        return 0.0, []
    jaccard = len(shared) / len(left | right)
    containment = len(shared) / min(len(left), len(right))
    return min(0.99, max(jaccard, containment * 0.92)), shared[:20]
