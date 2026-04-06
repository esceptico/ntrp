import asyncio
from typing import Protocol

from ntrp.agent import Role
from ntrp.constants import (
    COMPACTION_TIMEOUT,
    COMPRESSION_KEEP_RATIO,
    COMPRESSION_THRESHOLD,
    MAX_MESSAGES,
    SESSION_HANDOFF_MARKER,
    SUMMARY_MAX_TOKENS,
)
from ntrp.context.prompts import MERGE_SUMMARY_PROMPT_TEMPLATE, SUMMARIZE_PROMPT_TEMPLATE
from ntrp.llm.models import get_model
from ntrp.llm.router import get_completion_client
from ntrp.llm.utils import blocks_to_text


class Compactor(Protocol):
    async def maybe_compact(
        self,
        messages: list[dict],
        model: str,
        last_input_tokens: int | None,
    ) -> list[dict] | None:
        """Return compacted messages, or None if no compaction needed."""
        ...


def compact_needed(
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


def compactable_range(
    messages: list[dict],
    keep_ratio: float = COMPRESSION_KEEP_RATIO,
) -> tuple[int, int] | None:
    """Find (start, end) range of messages to summarize, or None if nothing to compact.

    Keeps the most recent `keep_ratio` fraction of messages (excluding system),
    snapping the boundary forward past tool messages to avoid splitting a turn.
    """
    n = len(messages)
    if n <= 4:
        return None

    compressible = n - 1
    keep_count = max(4, int(compressible * keep_ratio))
    tail_start = n - keep_count

    while tail_start < n and messages[tail_start]["role"] == Role.TOOL:
        tail_start += 1

    if tail_start <= 1 or tail_start >= n:
        return None

    return (1, tail_start)


def _extract_prior_summary(messages: list, start: int, end: int) -> str | None:
    """If the compactable range starts with a prior handoff, extract and return it."""
    if start >= end:
        return None
    content = blocks_to_text(messages[start].get("content", ""))
    if content.startswith(SESSION_HANDOFF_MARKER):
        return content.removeprefix(SESSION_HANDOFF_MARKER).strip()
    return None


def _build_conversation_text(messages: list, start: int, end: int, *, skip_handoff: bool = False) -> str:
    text_parts = []
    for msg in messages[start:end]:
        if (role := msg["role"]) == Role.TOOL:
            continue
        content = blocks_to_text(msg["content"])
        if not content:
            continue
        if content.startswith(SESSION_HANDOFF_MARKER):
            if skip_handoff:
                continue
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
            {"role": Role.SYSTEM, "content": prompt},
            {"role": Role.USER, "content": conversation_text},
        ],
        "temperature": 0.3,
        "max_tokens": summary_max_tokens,
    }


def _build_merge_request(
    existing_summary: str,
    new_conversation: str,
    model: str,
    summary_max_tokens: int = SUMMARY_MAX_TOKENS,
) -> dict:
    word_budget = int(summary_max_tokens * 0.75)
    prompt = MERGE_SUMMARY_PROMPT_TEMPLATE.render(budget=word_budget)
    user_content = f"## Existing Summary:\n{existing_summary}\n\n## New Conversation:\n{new_conversation}"
    return {
        "model": model,
        "messages": [
            {"role": Role.SYSTEM, "content": prompt},
            {"role": Role.USER, "content": user_content},
        ],
        "temperature": 0.3,
        "max_tokens": summary_max_tokens,
    }


async def compact_summarize(
    messages: list,
    start: int,
    end: int,
    model: str,
    summary_max_tokens: int = SUMMARY_MAX_TOKENS,
) -> str:
    prior_summary = _extract_prior_summary(messages, start, end)

    if prior_summary:
        new_start = start + 1
        new_conversation = _build_conversation_text(messages, new_start, end, skip_handoff=True)
        request = _build_merge_request(prior_summary, new_conversation, model, summary_max_tokens)
    else:
        conversation_text = _build_conversation_text(messages, start, end)
        request = _build_summarize_request(conversation_text, model, summary_max_tokens)

    client = get_completion_client(model)
    response = await asyncio.wait_for(
        client.completion(**request),
        timeout=COMPACTION_TIMEOUT,
    )
    content = response.choices[0].message.content
    if not content:
        return "Unable to summarize."
    return content.strip()


def _build_compacted_messages(messages: list[dict], end: int, summary: str) -> list[dict]:
    return [
        messages[0],
        {"role": Role.ASSISTANT, "content": f"{SESSION_HANDOFF_MARKER}\n{summary}"},
        *messages[end:],
    ]


async def compact_messages(
    messages: list[dict],
    model: str,
    *,
    keep_ratio: float = COMPRESSION_KEEP_RATIO,
    summary_max_tokens: int = SUMMARY_MAX_TOKENS,
) -> list[dict] | None:
    """Compact messages by summarizing old ones. Returns new messages or None if nothing to compact."""
    r = compactable_range(messages, keep_ratio=keep_ratio)
    if r is None:
        return None
    start, end = r
    summary = await compact_summarize(messages, start, end, model, summary_max_tokens)
    return _build_compacted_messages(messages, end, summary)


class SummaryCompactor:
    def __init__(
        self,
        threshold: float = COMPRESSION_THRESHOLD,
        max_messages: int = MAX_MESSAGES,
        keep_ratio: float = COMPRESSION_KEEP_RATIO,
        summary_max_tokens: int = SUMMARY_MAX_TOKENS,
    ):
        self.threshold = threshold
        self.max_messages = max_messages
        self.keep_ratio = keep_ratio
        self.summary_max_tokens = summary_max_tokens

    async def maybe_compact(
        self,
        messages: list[dict],
        model: str,
        last_input_tokens: int | None,
    ) -> list[dict] | None:
        if not compact_needed(
            messages,
            model,
            last_input_tokens,
            threshold=self.threshold,
            max_messages=self.max_messages,
        ):
            return None

        return await compact_messages(
            messages,
            model,
            keep_ratio=self.keep_ratio,
            summary_max_tokens=self.summary_max_tokens,
        )
