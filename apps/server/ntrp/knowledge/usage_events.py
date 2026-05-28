from collections import Counter
from collections.abc import Callable, Iterable
from typing import Any

from ntrp.knowledge.models import KnowledgeUsageObjectSummary
from ntrp.memory.models import MemoryAccessEvent

SummaryRow = dict[str, Any]
EnsureRow = Callable[[int], SummaryRow]


def _coerce_object_id(value: Any) -> int | None:
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.isdigit():
        object_id = int(value)
        return object_id if object_id > 0 else None
    return None


def _counter_dict(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def _new_row(object_id: int) -> SummaryRow:
    return {
        "object_id": object_id,
        "event_count": 0,
        "retrieved_count": 0,
        "selected_count": 0,
        "injected_count": 0,
        "omitted_count": 0,
        "used_by_model_count": 0,
        "model_visible_count": 0,
        "actually_used_count": 0,
        "last_activation_rank": None,
        "last_activation_score": None,
        "last_activation_surface": None,
        "last_selection_reason": None,
        "last_used_by_model": None,
        "last_activation_state": None,
        "last_model_visible": None,
        "last_actual_use_observed": None,
        "last_activation_reasons": [],
        "last_activation_task": None,
        "last_activation_task_id": None,
        "last_activation_session_id": None,
        "last_activation_run_id": None,
        "last_event_id": None,
        "last_seen_at": None,
    }


def _latest_trace_fields(item: dict[str, Any], *, reason: Any, surface: Any) -> dict[str, Any]:
    rank = item.get("rank")
    score = item.get("score")
    used_by_model = item.get("used_by_model")
    activation_state = item.get("activation_state")
    model_visible = item.get("model_visible")
    actual_use_observed = item.get("actual_use_observed")
    reasons = item.get("reasons")
    reason_list = [value for value in reasons if isinstance(value, str)] if isinstance(reasons, list) else []
    return {
        "last_activation_rank": rank if isinstance(rank, int) else None,
        "last_activation_score": score if isinstance(score, (int, float)) else None,
        "last_activation_surface": surface if isinstance(surface, str) and surface else None,
        "last_selection_reason": reason if isinstance(reason, str) and reason else None,
        "last_used_by_model": used_by_model if isinstance(used_by_model, bool) else None,
        "last_activation_state": activation_state if activation_state in {"injected", "selected_not_injected", "omitted"} else None,
        "last_model_visible": model_visible if isinstance(model_visible, bool) else None,
        "last_actual_use_observed": actual_use_observed if isinstance(actual_use_observed, bool) else None,
        "last_activation_reasons": reason_list,
    }


def _latest_event_fields(details: dict[str, Any]) -> dict[str, str | None]:
    return {
        "last_activation_task": details.get("task") if isinstance(details.get("task"), str) else None,
        "last_activation_task_id": details.get("task_id") if isinstance(details.get("task_id"), str) else None,
        "last_activation_session_id": (
            details.get("session_id") if isinstance(details.get("session_id"), str) else None
        ),
        "last_activation_run_id": details.get("run_id") if isinstance(details.get("run_id"), str) else None,
    }


def _increment_membership_counts(event: MemoryAccessEvent, ensure: EnsureRow) -> set[int]:
    object_ids_seen: set[int] = set()
    for field_name, count_name in (
        ("retrieved_fact_ids", "retrieved_count"),
        ("injected_fact_ids", "injected_count"),
        ("omitted_fact_ids", "omitted_count"),
    ):
        for object_id in getattr(event, field_name):
            ensure(object_id)[count_name] += 1
            object_ids_seen.add(object_id)
    return object_ids_seen


def _record_trace_items(
    details: dict[str, Any],
    *,
    ensure: EnsureRow,
    object_ids_seen: set[int],
    selection_reasons: dict[int, Counter[str]],
    surfaces: dict[int, Counter[str]],
) -> None:
    for trace_key in ("candidates", "omitted"):
        trace_items = details.get(trace_key)
        if not isinstance(trace_items, list):
            continue
        for item in trace_items:
            if not isinstance(item, dict):
                continue
            object_id = _coerce_object_id(item.get("object_id"))
            if object_id is None:
                continue
            row = ensure(object_id)
            object_ids_seen.add(object_id)
            if item.get("selected") is True:
                row["selected_count"] += 1
            if item.get("used_by_model") is True:
                row["used_by_model_count"] += 1
            if item.get("model_visible") is True or ("model_visible" not in item and item.get("injected") is True):
                row["model_visible_count"] += 1
            if item.get("actual_use_observed") is True:
                row["actually_used_count"] += 1
            reason = item.get("selection_reason")
            if isinstance(reason, str) and reason:
                selection_reasons[object_id][reason] += 1
            surface = item.get("surface")
            if isinstance(surface, str) and surface:
                surfaces[object_id][surface] += 1
            if row["last_event_id"] is None:
                row.update(_latest_trace_fields(item, reason=reason, surface=surface))


def _record_feedback_outcomes(
    event: MemoryAccessEvent,
    details: dict[str, Any],
    *,
    ensure: EnsureRow,
    object_ids_seen: set[int],
    outcomes: dict[int, Counter[str]],
) -> None:
    feedback_by_object = details.get("feedback_by_object")
    object_feedback_seen = False
    if isinstance(feedback_by_object, dict):
        for raw_object_id, raw_feedback in feedback_by_object.items():
            object_id = _coerce_object_id(raw_object_id)
            if object_id is None or not isinstance(raw_feedback, dict):
                continue
            outcome = raw_feedback.get("outcome")
            if not isinstance(outcome, str) or not outcome:
                continue
            ensure(object_id)
            outcomes[object_id][outcome] += 1
            object_ids_seen.add(object_id)
            object_feedback_seen = True

    outcome = details.get("outcome")
    if object_feedback_seen or not isinstance(outcome, str) or not outcome:
        return
    target_ids = details.get("target_object_ids")
    if isinstance(target_ids, list):
        outcome_object_ids = [_coerce_object_id(value) for value in target_ids]
    else:
        # Outcome feedback without explicit targets is event-level. Apply it only
        # to injected memories because those reached the model.
        outcome_object_ids = event.injected_fact_ids
    for object_id in outcome_object_ids:
        if object_id is None:
            continue
        ensure(object_id)
        outcomes[object_id][outcome] += 1
        object_ids_seen.add(object_id)


def _mark_seen(
    event: MemoryAccessEvent,
    object_ids_seen: set[int],
    details: dict[str, Any],
    ensure: EnsureRow,
) -> None:
    for object_id in object_ids_seen:
        row = ensure(object_id)
        row["event_count"] += 1
        if row["last_event_id"] is None:
            row.update(_latest_event_fields(details))
            row["last_event_id"] = event.id
            row["last_seen_at"] = event.created_at


def summarize_activation_usage_events(events: Iterable[MemoryAccessEvent]) -> list[KnowledgeUsageObjectSummary]:
    rows: dict[int, SummaryRow] = {}
    selection_reasons: dict[int, Counter[str]] = {}
    surfaces: dict[int, Counter[str]] = {}
    outcomes: dict[int, Counter[str]] = {}

    def ensure(object_id: int) -> SummaryRow:
        row = rows.get(object_id)
        if row is None:
            row = _new_row(object_id)
            rows[object_id] = row
            selection_reasons[object_id] = Counter()
            surfaces[object_id] = Counter()
            outcomes[object_id] = Counter()
        return row

    for event in events:
        object_ids_seen = _increment_membership_counts(event, ensure)
        details = event.details or {}
        _record_trace_items(
            details,
            ensure=ensure,
            object_ids_seen=object_ids_seen,
            selection_reasons=selection_reasons,
            surfaces=surfaces,
        )
        _record_feedback_outcomes(
            event,
            details,
            ensure=ensure,
            object_ids_seen=object_ids_seen,
            outcomes=outcomes,
        )
        _mark_seen(event, object_ids_seen, details, ensure)

    summaries = []
    for object_id, row in rows.items():
        summaries.append(
            KnowledgeUsageObjectSummary(
                **row,
                selection_reasons=_counter_dict(selection_reasons[object_id]),
                surfaces=_counter_dict(surfaces[object_id]),
                outcome_counts=_counter_dict(outcomes[object_id]),
            )
        )
    return sorted(summaries, key=lambda item: (item.last_seen_at is None, item.last_seen_at), reverse=True)
