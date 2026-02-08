from ntrp.constants import (
    CHARS_PER_TOKEN,
    COMPRESSION_THRESHOLD,
    MASK_PREVIEW_CHARS,
    MASK_THRESHOLD,
    SUPPORTED_MODELS,
    TAIL_TOKEN_BUDGET,
)
from ntrp.context.prompts import SUMMARIZE_PROMPT_TEMPLATE
from ntrp.llm import acompletion


# TO CLAUDE: do we need this function? looks dirty
def _get_attr(msg, key: str, default=None):
    if isinstance(msg, dict):
        return msg.get(key, default)
    return getattr(msg, key, default)


def _count_message_tokens(msg) -> int:  # TO CLAUDE: this is approx function, do we have real token compute? (litellm must return this info)
    total_chars = 16

    content = _get_attr(msg, "content")
    if isinstance(content, str):
        total_chars += len(content)

    role = _get_attr(msg, "role")
    if role:
        total_chars += len(role)

    tool_calls = _get_attr(msg, "tool_calls")
    if tool_calls:
        for tc in tool_calls:
            func = getattr(tc, "function", None)
            if func:
                total_chars += len(func.name or "")
                total_chars += len(func.arguments or "")

    return total_chars // CHARS_PER_TOKEN


def count_tokens(messages: list) -> int:
    return sum(_count_message_tokens(msg) for msg in messages)


def should_compress(
    messages: list[dict],
    model: str,
    actual_input_tokens: int | None = None,
) -> bool:
    limit = SUPPORTED_MODELS[model]["tokens"]

    if actual_input_tokens is not None:
        return actual_input_tokens > int(limit * 0.80)  # TO CLAUDE: why 0.8 here?

    threshold = int(limit * COMPRESSION_THRESHOLD)
    current = count_tokens(messages)
    return current > threshold


def find_compressible_range(
    messages: list[dict],
    tail_token_budget: int = TAIL_TOKEN_BUDGET,
) -> tuple[int, int]:
    if len(messages) <= 3:
        return (0, 0)

    tail_tokens = 0
    tail_start = len(messages)

    for i in range(len(messages) - 1, 0, -1):
        msg_tokens = _count_message_tokens(messages[i])
        if tail_tokens + msg_tokens > tail_token_budget:
            break
        tail_tokens += msg_tokens
        tail_start = i

    tail_start = min(tail_start, len(messages) - 4)

    while tail_start < len(messages) and messages[tail_start].get("role") == "tool":
        tail_start += 1

    start = 1
    end = tail_start

    if end <= start:
        return (0, 0)

    return (start, end)


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
    # Scale budget: ~1 summary token per 4 input tokens, clamped to [400, 2000]
    input_tokens = len(conversation_text) // CHARS_PER_TOKEN
    max_tokens = max(400, min(2000, input_tokens // 4))
    # ~0.75 words per token
    word_budget = int(max_tokens * 0.75)
    prompt = SUMMARIZE_PROMPT_TEMPLATE.format(budget=word_budget)
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": conversation_text},
        ],
        "temperature": 0.3,
        "max_tokens": max_tokens,
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
