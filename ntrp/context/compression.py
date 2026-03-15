from ntrp.constants import (
    COMPRESSION_KEEP_RATIO,
    COMPRESSION_THRESHOLD,
    MAX_MESSAGES,
    SUMMARY_MAX_TOKENS,
)
from ntrp.context.prompts import SUMMARIZE_PROMPT_TEMPLATE
from ntrp.llm.models import get_model
from ntrp.llm.router import get_completion_client


def should_compress(
    messages: list[dict],
    model: str,
    actual_input_tokens: int | None = None,
    *,
    threshold: float = COMPRESSION_THRESHOLD,
    max_messages: int = MAX_MESSAGES,
) -> bool:
    if len(messages) > max_messages:
        return True

    if actual_input_tokens is not None:
        limit = get_model(model).max_context_tokens
        return actual_input_tokens > int(limit * threshold)

    return False


def find_compressible_range(
    messages: list[dict],
    keep_ratio: float = COMPRESSION_KEEP_RATIO,
) -> tuple[int, int] | None:
    """Find (start, end) range of messages to summarize, or None if nothing to compress.

    Keeps the most recent `keep_ratio` fraction of messages (excluding system),
    snapping the boundary forward past tool messages to avoid splitting a turn.
    """
    n = len(messages)
    if n <= 4:
        return None

    # messages[0] is system — compressible range starts at 1
    compressible = n - 1  # messages after system
    keep_count = max(4, int(compressible * keep_ratio))
    tail_start = n - keep_count

    # Snap forward past tool messages to avoid splitting mid-turn
    while tail_start < n and messages[tail_start]["role"] == "tool":
        tail_start += 1

    if tail_start <= 1:
        return None

    return (1, tail_start)


def _build_conversation_text(messages: list, start: int, end: int) -> str:
    text_parts = []
    for msg in messages[start:end]:
        if (role := msg["role"]) == "tool":
            continue
        if not (content := msg["content"]):
            continue
        if content.startswith("[Session State Handoff]"):
            text_parts.append(f"[PRIOR SUMMARY — preserve key points]\n{content}")
        else:
            text_parts.append(f"{role}: {content}")
    return "\n\n".join(text_parts)


def _build_summarize_request(conversation_text: str, model: str, summary_max_tokens: int = SUMMARY_MAX_TOKENS) -> dict:
    word_budget = int(summary_max_tokens * 0.75)
    prompt = SUMMARIZE_PROMPT_TEMPLATE.render(budget=word_budget)
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": conversation_text},
        ],
        "temperature": 0.3,
        "max_tokens": summary_max_tokens,
    }


async def summarize_messages_async(
    messages: list,
    start: int,
    end: int,
    model: str,
    summary_max_tokens: int = SUMMARY_MAX_TOKENS,
) -> str:
    conversation_text = _build_conversation_text(messages, start, end)
    client = get_completion_client(model)
    response = await client.completion(**_build_summarize_request(conversation_text, model, summary_max_tokens))
    content = response.choices[0].message.content
    if not content:
        return "Unable to summarize."
    return content.strip()


def _build_compressed_messages(messages: list[dict], end: int, summary: str) -> list[dict]:
    return [
        messages[0],
        {"role": "assistant", "content": f"[Session State Handoff]\n{summary}"},
        *messages[end:],
    ]


async def compress_context_async(
    messages: list[dict],
    model: str,
    on_compress=None,
    force: bool = False,
    keep_ratio: float = COMPRESSION_KEEP_RATIO,
    summary_max_tokens: int = SUMMARY_MAX_TOKENS,
) -> tuple[list[dict], bool]:
    if not force and not should_compress(messages, model):
        return messages, False

    compressible = find_compressible_range(messages, keep_ratio=keep_ratio)
    if compressible is None:
        return messages, False
    start, end = compressible

    if on_compress:
        await on_compress(f"compressing context ({end - start} messages)...")

    summary = await summarize_messages_async(messages, start, end, model, summary_max_tokens)
    return _build_compressed_messages(messages, end, summary), True
