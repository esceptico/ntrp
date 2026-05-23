import re

_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "can",
    "check",
    "could",
    "current",
    "find",
    "fix",
    "for",
    "help",
    "in",
    "inspect",
    "into",
    "it",
    "look",
    "me",
    "of",
    "on",
    "opportunities",
    "please",
    "research",
    "search",
    "the",
    "this",
    "to",
    "we",
    "with",
    "you",
}

_ACRONYMS = {
    "api",
    "ci",
    "css",
    "db",
    "html",
    "json",
    "llm",
    "mcp",
    "oauth",
    "sse",
    "sql",
    "ui",
    "ux",
}


def _words(text: str) -> list[str]:
    return [part.lower() for part in re.findall(r"[A-Za-z0-9]+", text)]


def _display_word(word: str) -> str:
    if word in _ACRONYMS:
        return word.upper()
    return word.capitalize()


def _title(text: str, *, fallback: str, max_words: int) -> str:
    words = [word for word in _words(text) if word not in _STOPWORDS]
    selected = words[:max_words]
    if not selected:
        return fallback
    return " ".join(_display_word(word) for word in selected)


def _role_title(kind: str) -> str:
    words = [
        word
        for word in _words(kind.replace("_agent", "").replace("-", " "))
        if word not in {"agent", "sub"}
    ]
    if not words:
        return "Agent"
    return _display_word(words[0])


def conversation_name(text: str, *, has_images: bool = False) -> str:
    if not text.strip() and has_images:
        return "Image Conversation"
    return _title(text, fallback="New Conversation", max_words=4)


def agent_name(kind: str, task: str) -> str:
    role = _role_title(kind)
    topic = _title(task, fallback="Task", max_words=3)
    if topic == "Task":
        return role
    return f"{role} {topic}"
