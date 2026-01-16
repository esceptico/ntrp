import json
from datetime import datetime

import litellm

from ntrp.constants import (
    COMPRESSION_THRESHOLD,
    MASK_PREVIEW_CHARS,
    MASK_THRESHOLD,
    SUPPORTED_MODELS,
    TAIL_TOKEN_BUDGET,
)
from ntrp.context.models import SessionState
from ntrp.context.prompts import SUMMARIZE_PROMPT

CHARS_PER_TOKEN = 4


def _get_attr(msg, key: str, default=None):
    if isinstance(msg, dict):
        return msg.get(key, default)
    return getattr(msg, key, default)


def count_tokens(messages: list, model: str) -> int:
    total_chars = 0

    for msg in messages:
        total_chars += 16

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


def should_compress(messages: list[dict], model: str) -> bool:
    limit = SUPPORTED_MODELS[model]["tokens"]
    threshold = int(limit * COMPRESSION_THRESHOLD)
    current = count_tokens(messages, model)
    return current > threshold


def _count_message_tokens(msg) -> int:
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
            text_parts.append(f"{role}: {content}")
    return "\n\n".join(text_parts)


def _build_summarize_request(conversation_text: str, model: str) -> dict:
    model_params = SUPPORTED_MODELS[model]
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": SUMMARIZE_PROMPT},
            {"role": "user", "content": conversation_text},
        ],
        "temperature": 0.3,
        "max_tokens": 800,
        **model_params.get("request_kwargs", {}),
    }


def summarize_messages_sync(
    messages: list,
    start: int,
    end: int,
    model: str,
) -> str:
    conversation_text = _build_conversation_text(messages, start, end)
    response = litellm.completion(**_build_summarize_request(conversation_text, model))
    return response.choices[0].message.content or "Unable to summarize."


async def summarize_messages_async(
    messages: list,
    start: int,
    end: int,
    model: str,
) -> str:
    conversation_text = _build_conversation_text(messages, start, end)
    response = await litellm.acompletion(**_build_summarize_request(conversation_text, model))
    return response.choices[0].message.content or "Unable to summarize."


def _build_compressed_messages(messages: list[dict], end: int, summary: str) -> list[dict]:
    return [
        messages[0],
        {"role": "assistant", "content": f"[Session State Handoff]\n{summary}"},
        *messages[end:],
    ]


def compress_context_sync(
    messages: list[dict],
    model: str,
) -> list[dict]:
    if not should_compress(messages, model):
        return messages

    start, end = find_compressible_range(messages)
    if start == 0 and end == 0:
        return messages

    summary = summarize_messages_sync(messages, start, end, model)
    return _build_compressed_messages(messages, end, summary)


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


def sanitize_history_for_model(messages: list[dict]) -> list[dict]:
    sanitized = []
    i = 0

    while i < len(messages):
        msg = messages[i]
        role = msg.get("role", "")

        if role == "system":
            sanitized.append({"role": "system", "content": msg.get("content", "")})
            i += 1
            continue

        if role == "user":
            sanitized.append({"role": "user", "content": msg.get("content", "")})
            i += 1
            continue

        if role == "assistant" and msg.get("tool_calls"):
            tool_summaries = []

            for tc in msg.get("tool_calls", []):
                func = tc.get("function", {})
                tool_name = func.get("name", "unknown")
                args_str = func.get("arguments", "{}")
                try:
                    args = json.loads(args_str) if args_str else {}
                    main_arg = next(iter(args.values()), "") if args else ""
                    if isinstance(main_arg, str) and len(main_arg) > 100:
                        main_arg = main_arg[:100] + "..."
                except (json.JSONDecodeError, TypeError):
                    main_arg = ""

                tool_summaries.append(f"[{tool_name}({main_arg})]")

            results = []
            j = i + 1
            while j < len(messages) and messages[j].get("role") == "tool":
                result_content = messages[j].get("content", "")
                if len(result_content) > 200:
                    result_content = result_content[:200] + "..."
                results.append(result_content)
                j += 1

            summary_parts = []
            if msg.get("content"):
                summary_parts.append(msg["content"])
            summary_parts.append("Called: " + ", ".join(tool_summaries))
            if results:
                summary_parts.append("Results: " + " | ".join(results))

            sanitized.append({"role": "assistant", "content": "\n".join(summary_parts)})

            i = j
            continue

        if role == "assistant":
            sanitized.append(msg)
            i += 1
            continue

        if role == "tool":
            i += 1
            continue

        sanitized.append(msg)
        i += 1

    return sanitized


class SessionManager:
    def __init__(
        self,
        model: str,
        max_turns: int = 20,
        idle_seconds: int = 900,
    ) -> None:
        self.model = model
        self.max_turns = max_turns
        self.idle_seconds = idle_seconds

    def should_compact(self, session: SessionState, messages: list) -> bool:
        return should_compress(messages, self.model)

    async def compact_session(
        self,
        session: SessionState,
        messages: list[dict],
        on_compress=None,
        force: bool = False,
    ) -> tuple[SessionState, list[dict], bool]:
        new_messages, was_compressed = await compress_context_async(
            messages, self.model, on_compress=on_compress, force=force
        )

        if was_compressed:
            session.last_compaction_turn = len(new_messages)
            for msg in new_messages:
                if msg.get("role") == "assistant" and isinstance(msg.get("content"), str):
                    content = msg.get("content", "")
                    if content.startswith("[Session State Handoff]"):
                        session.rolling_summary = content
                        break
        else:
            session.last_compaction_turn = len(messages)

        session.last_activity = datetime.now()
        return session, new_messages, was_compressed
