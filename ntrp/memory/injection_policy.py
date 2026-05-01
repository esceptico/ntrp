from collections import Counter
from typing import Any

from ntrp.memory.models import MemoryAccessEvent

DEFAULT_INJECTION_CHAR_BUDGET = 3000


def memory_injection_policy_preview(
    events: list[MemoryAccessEvent],
    *,
    char_budget: int = DEFAULT_INJECTION_CHAR_BUDGET,
) -> dict[str, Any]:
    budget = max(1, char_budget)
    by_source = Counter(event.source for event in events)
    total_chars = sum(event.formatted_chars for event in events)
    candidates = [_candidate(event, budget) for event in events]
    candidates = [candidate for candidate in candidates if candidate is not None]

    return {
        "policy": {
            "char_budget": budget,
            "version": "memory.injection.preview.v1",
        },
        "summary": {
            "events": len(events),
            "sources": dict(sorted(by_source.items())),
            "average_chars": round(total_chars / len(events), 1) if events else 0,
            "max_chars": max((event.formatted_chars for event in events), default=0),
            "empty_recalls": sum(1 for candidate in candidates if "empty_recall" in candidate["reasons"]),
            "over_budget": sum(1 for candidate in candidates if "over_budget" in candidate["reasons"]),
            "pattern_heavy": sum(1 for candidate in candidates if "pattern_heavy" in candidate["reasons"]),
            "candidates": len(candidates),
        },
        "candidates": candidates,
    }


def _candidate(event: MemoryAccessEvent, char_budget: int) -> dict[str, Any] | None:
    fact_count = len(event.injected_fact_ids)
    pattern_count = len(event.injected_observation_ids)
    injected_count = fact_count + pattern_count

    reasons: list[str] = []
    if event.source == "recall_tool" and event.query and injected_count == 0:
        reasons.append("empty_recall")
    if event.formatted_chars > char_budget:
        reasons.append("over_budget")
    if pattern_count >= 3 and pattern_count > fact_count * 2:
        reasons.append("pattern_heavy")

    if not reasons:
        return None

    return {
        "access_event_id": event.id,
        "created_at": event.created_at.isoformat(),
        "source": event.source,
        "query": event.query,
        "formatted_chars": event.formatted_chars,
        "fact_count": fact_count,
        "pattern_count": pattern_count,
        "reasons": reasons,
        "recommendation": _recommendation(reasons),
    }


def _recommendation(reasons: list[str]) -> str:
    if "over_budget" in reasons:
        return "tighten injected context budget before adding more memory"
    if "pattern_heavy" in reasons:
        return "prefer source facts or profile facts over broad derived patterns"
    if "empty_recall" in reasons:
        return "review recall phrasing or retrieval coverage for this query"
    return "review"
