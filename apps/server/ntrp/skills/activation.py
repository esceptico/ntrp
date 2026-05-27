from __future__ import annotations

from typing import TYPE_CHECKING

from ntrp.logging import get_logger
from ntrp.memory.activation import ActivationSkillSuggestion, MemoryActivationBundle
from ntrp.skills.registry import SkillRegistry

if TYPE_CHECKING:
    from ntrp.memory.service import MemoryService

_logger = get_logger(__name__)

ActivatedSkillEntry = tuple[ActivationSkillSuggestion, str]


def append_context_block(existing: str | None, block: str | None) -> str | None:
    if not block:
        return existing
    if not existing:
        return block
    return f"{existing}\n\n{block}"


def activated_skill_entries(
    bundle: MemoryActivationBundle, registry: SkillRegistry | None, *, max_skills: int = 1
) -> list[ActivatedSkillEntry]:
    # Slice 3 retrieval deliberately returns no skill suggestions; slice 7 wires
    # the skill inducer and toolability gate back into this existing formatter.
    if registry is None or not bundle.skills_to_use or max_skills <= 0:
        return []
    entries: list[ActivatedSkillEntry] = []
    seen: set[str] = set()
    args = f"Current user request: {bundle.query}"
    for suggestion in bundle.skills_to_use:
        if len(entries) >= max_skills:
            break
        if suggestion.skill_name in seen:
            continue
        seen.add(suggestion.skill_name)
        skill_xml = registry.render_skill_xml(suggestion.skill_name, args=args)
        if skill_xml:
            entries.append((suggestion, skill_xml))
    return entries


def format_activated_skill_context(entries: list[ActivatedSkillEntry]) -> str | None:
    if not entries:
        return None
    return "<activated_skills>\n" + "\n\n".join(skill_xml for _, skill_xml in entries) + "\n</activated_skills>"


def render_activated_skill_context(
    bundle: MemoryActivationBundle, registry: SkillRegistry | None, *, max_skills: int = 1
) -> str | None:
    return format_activated_skill_context(activated_skill_entries(bundle, registry, max_skills=max_skills))


async def record_auto_activated_skill_events(
    memory_service: MemoryService | None,
    bundle: MemoryActivationBundle,
    registry: SkillRegistry | None,
    *,
    task: str,
    activation_surface: str,
    task_id: str | None,
    session_id: str | None,
    run_id: str | None,
    max_skills: int = 1,
    entries: list[ActivatedSkillEntry] | None = None,
) -> None:
    access_events = getattr(memory_service, "access_events", None) if memory_service is not None else None
    if access_events is None:
        return
    selected_entries = entries if entries is not None else activated_skill_entries(bundle, registry, max_skills=max_skills)
    for suggestion, _ in selected_entries:
        meta = registry.get(suggestion.skill_name) if registry is not None else None
        details = {
            "task": task,
            "task_id": task_id,
            "session_id": session_id,
            "run_id": run_id,
            "surface": "skill",
            "activation_surface": activation_surface,
            "skill_name": suggestion.skill_name,
            "skill_args": f"Current user request: {bundle.query}",
            "triggering_usage_event_id": bundle.usage_event_id,
            "triggering_memory_object_id": suggestion.object_id,
            "selection_score": suggestion.score,
            "selection_reasons": suggestion.reasons,
        }
        if meta is not None:
            details["skill_path"] = str(meta.path)
            details["skill_location"] = meta.location
            if meta.source:
                details["skill_source"] = meta.source
        try:
            await access_events.create(
                source="skill_activation",
                query=suggestion.skill_name,
                policy_version="skills.auto_activation.v1",
                details=details,
            )
        except Exception:
            _logger.exception("Failed to record auto skill activation telemetry", skill=suggestion.skill_name)
