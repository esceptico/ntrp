import asyncio
import re
from typing import Any

from ntrp.logging import get_logger
from ntrp.memory.facts import FactMemory, SessionMemory
from ntrp.memory.formatting import format_memory_context_render, model_memory_context
from ntrp.memory.models import FactContext

_logger = get_logger(__name__)

MEMORY_PREFETCH_TIMEOUT_SECONDS = 0.75
MEMORY_PREFETCH_CONTEXT_BUDGET = 1200
MEMORY_PREFETCH_RECALL_LIMIT = 3
MEMORY_PREFETCH_MIN_WORDS = 2
_PREFETCH_WORD_RE = re.compile(r"\b[\w-]{3,}\b")


def memory_prefetch_query(user_message: str) -> str | None:
    query = user_message.strip()
    if not query or query.startswith("/"):
        return None
    if len(_PREFETCH_WORD_RE.findall(query)) < MEMORY_PREFETCH_MIN_WORDS:
        return None
    return query[:1000]


def filter_prefetch_context(context: FactContext, session_memory: SessionMemory) -> FactContext:
    session_fact_ids = {fact.id for fact in session_memory.profile_facts}
    session_fact_ids.update(fact.id for fact in session_memory.user_facts)
    session_observation_ids = {observation.id for observation in session_memory.observations}
    for observation in session_memory.observations:
        session_fact_ids.update(observation.source_fact_ids)

    return context.model_copy(
        update={
            "facts": [fact for fact in context.facts if fact.id not in session_fact_ids],
            "observations": [
                observation for observation in context.observations if observation.id not in session_observation_ids
            ],
            "bundled_sources": {
                observation_id: [fact for fact in facts if fact.id not in session_fact_ids]
                for observation_id, facts in context.bundled_sources.items()
                if observation_id not in session_observation_ids
            },
        }
    )


async def prefetch_memory_context(
    memory: FactMemory,
    user_message: str,
    session_memory: SessionMemory | None = None,
    *,
    source: str,
    details: dict[str, Any] | None = None,
    timeout_seconds: float = MEMORY_PREFETCH_TIMEOUT_SECONDS,
    recall_limit: int = MEMORY_PREFETCH_RECALL_LIMIT,
    context_budget: int = MEMORY_PREFETCH_CONTEXT_BUDGET,
) -> str | None:
    query = memory_prefetch_query(user_message)
    if query is None:
        return None
    try:
        context = await asyncio.wait_for(
            memory.inspect_recall(query=query, limit=recall_limit),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        _logger.debug("Memory prefetch timed out")
        return None
    except Exception as e:
        _logger.warning("Memory prefetch failed: %s", e)
        return None

    if session_memory is not None:
        context = filter_prefetch_context(context, session_memory)
    context = model_memory_context(context)
    rendered = format_memory_context_render(
        query_facts=context.facts,
        query_observations=context.observations,
        bundled_sources=context.bundled_sources,
        budget=context_budget,
    )
    if rendered is None:
        return None

    await memory.record_context_access(
        source=source,
        query=query,
        context=context,
        formatted_chars=len(rendered.text),
        injected_fact_ids=rendered.fact_ids,
        injected_observation_ids=rendered.observation_ids,
        bundled_fact_ids=rendered.bundled_fact_ids,
        details={"timeout_seconds": timeout_seconds, **(details or {})},
    )
    return rendered.text
