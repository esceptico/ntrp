from ntrp.constants import (
    COMPRESSION_KEEP_RATIO,
    COMPRESSION_THRESHOLD,
    MASK_PREVIEW_CHARS,
    MASK_THRESHOLD,
    MAX_MESSAGES,
    SUMMARY_MAX_TOKENS,
    SUPPORTED_MODELS,
)
from ntrp.context.prompts import SUMMARIZE_PROMPT_TEMPLATE
from ntrp.llm import acompletion


def _get_attr(msg, key: str, default=None):
    if isinstance(msg, dict):
        return msg.get(key, default)
    return getattr(msg, key, default)


def should_compress(
    messages: list[dict],
    model: str,
    actual_input_tokens: int | None = None,
) -> bool:
    if len(messages) > MAX_MESSAGES:
        return True

    if actual_input_tokens is not None:
        limit = SUPPORTED_MODELS[model]["tokens"]
        return actual_input_tokens > int(limit * COMPRESSION_THRESHOLD)

    return False


def find_compressible_range(
    messages: list[dict],
    keep_ratio: float = COMPRESSION_KEEP_RATIO,
) -> tuple[int, int]:
    """Find (start, end) range of messages to summarize.

    Keeps the most recent `keep_ratio` fraction of messages (excluding system),
    snapping the boundary forward past tool messages to avoid splitting a turn.
    Returns (0, 0) if there's nothing worth compressing.
    """
    n = len(messages)
    if n <= 4:
        return (0, 0)

    # messages[0] is system — compressible range starts at 1
    compressible = n - 1  # messages after system
    keep_count = max(4, int(compressible * keep_ratio))
    tail_start = n - keep_count

    # Snap forward past tool messages to avoid splitting mid-turn
    while tail_start < n and messages[tail_start].get("role") == "tool":
        tail_start += 1

    if tail_start <= 1:
        return (0, 0)

    return (1, tail_start)


def _build_conversation_text(messages: list, start: int, end: int) -> str:
    text_parts = []
    for msg in messages[start:end]:
        role = _get_attr(msg, "role") or "unknown"
        content = _get_attr(msg, "content") or ""
        if isinstance(content, str) and content:
            # Preserve previous summaries verbatim — don't let them get re-summarized
            if content.startswith("[Session State Handoff]"):
                text_parts.append(f"[PRIOR SUMMARY — preserve key points]\n{content}")
            else:
                text_parts.append(f"{role}: {content}")
    return "\n\n".join(text_parts)


def _build_summarize_request(conversation_text: str, model: str) -> dict:
    model_params = SUPPORTED_MODELS[model]
    word_budget = int(SUMMARY_MAX_TOKENS * 0.75)
    prompt = SUMMARIZE_PROMPT_TEMPLATE.format(budget=word_budget)
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": conversation_text},
        ],
        "temperature": 0.3,
        "max_tokens": SUMMARY_MAX_TOKENS,
        **model_params.get("request_kwargs", {}),
    }


async def summarize_messages_async(
    messages: list,
    start: int,
    end: int,
    model: str,
) -> str:
    conversation_text = _build_conversation_text(messages, start, end)
    response = await acompletion(**_build_summarize_request(conversation_text, model))
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
) -> tuple[list[dict], bool]:
    if not force and not should_compress(messages, model):
        return messages, False

    start, end = find_compressible_range(messages)
    if start == 0 and end == 0:
        return messages, False

    if on_compress:
        await on_compress(f"compressing context ({end - start} messages)...")

    summary = await summarize_messages_async(messages, start, end, model)
    return _build_compressed_messages(messages, end, summary), True


def mask_old_tool_results(messages: list[dict], preserve_recent: int = 6) -> list[dict]:
    tool_indices = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
    if not tool_indices:
        return messages

    recent = set(tool_indices[-preserve_recent:])

    result = []
    for i, msg in enumerate(messages):
        if msg.get("role") == "tool" and i not in recent:
            content = msg.get("content", "")
            if len(content) > MASK_THRESHOLD:
                masked = content[:MASK_PREVIEW_CHARS] + f"\n[...{len(content) - MASK_PREVIEW_CHARS} chars masked]"
                result.append({**msg, "content": masked})
            else:
                result.append(msg)
        else:
            result.append(msg)
    return result
