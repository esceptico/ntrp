import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel

from ntrp.automation.prompts import AUTOMATION_SUGGESTER_SYSTEM
from ntrp.automation.triggers import Trigger, build_trigger
from ntrp.constants import MAX_AUTOMATION_SUGGESTIONS
from ntrp.logging import get_logger
from ntrp.memory.models import Scope, ScopeKind

_logger = get_logger(__name__)

SuggestionStatus = Literal["active", "dismissed", "accepted"]


@dataclass
class AutomationSuggestion:
    id: str
    name: str
    description: str
    triggers: list[Trigger]
    rationale: str
    category: str
    evidence: list[str] = field(default_factory=list)
    icon: str | None = None
    status: SuggestionStatus = "active"
    created_at: datetime | None = None
    source_automation_id: str | None = None


class ScheduleDraft(BaseModel):
    trigger_type: Literal["time", "event"]
    at: str | None = None
    days: str | None = None
    every: str | None = None
    event_type: str | None = None
    lead_minutes: int | None = None


class SuggestionDraft(BaseModel):
    name: str
    prompt: str
    schedule: ScheduleDraft
    rationale: str
    category: str
    evidence: list[str] = []
    icon: str | None = None


class SuggestionSet(BaseModel):
    suggestions: list[SuggestionDraft]


_USER_SCOPE = Scope(kind=ScopeKind.USER)
_MAX_SUBJECTS = 30
_MAX_CLAIMS = 40
_MAX_SESSIONS = 20


class AutomationSuggester:
    def __init__(self, *, memory, sessions, automations, cheap_llm, model):
        self.memory = memory
        self.sessions = sessions
        self.automations = automations
        self.cheap_llm = cheap_llm
        self.model = model

    async def run(self) -> str:
        context = await self._gather()
        response = await self.cheap_llm.completion(
            messages=[
                {"role": "system", "content": AUTOMATION_SUGGESTER_SYSTEM},
                {"role": "user", "content": context},
            ],
            model=self.model,
            response_format=SuggestionSet,
        )
        drafts = self._parse(response).suggestions

        kept: list[AutomationSuggestion] = []
        dropped = 0
        now = datetime.now(UTC)
        for draft in drafts:
            triggers = self._validate(draft)
            if triggers is None:
                dropped += 1
                continue
            kept.append(
                AutomationSuggestion(
                    id=str(uuid.uuid4()),
                    name=draft.name,
                    description=draft.prompt,
                    triggers=triggers,
                    rationale=draft.rationale,
                    category=draft.category,
                    evidence=draft.evidence,
                    icon=draft.icon,
                    created_at=now,
                )
            )
            if len(kept) >= MAX_AUTOMATION_SUGGESTIONS:
                break

        await self.automations.replace_active_suggestions(kept)
        return f"suggestions={len(kept)}; dropped={dropped}"

    def _parse(self, response) -> SuggestionSet:
        content = response.choices[0].message.content
        if isinstance(content, SuggestionSet):
            return content
        return SuggestionSet.model_validate_json(content)

    def _validate(self, draft: SuggestionDraft) -> list[Trigger] | None:
        schedule = draft.schedule
        try:
            trigger, _ = build_trigger(
                schedule.trigger_type,
                at=schedule.at,
                days=schedule.days,
                every=schedule.every,
                event_type=schedule.event_type,
                lead_minutes=schedule.lead_minutes,
            )
        except ValueError as e:
            _logger.warning("Dropping suggestion %r with invalid schedule: %s", draft.name, e)
            return None
        return [trigger]

    async def _gather(self) -> str:
        sections: list[str] = []

        subjects = await self._memory_subjects()
        if subjects:
            sections.append("Memory subjects (subject — active claims):\n" + subjects)

        claims = await self._recent_claims()
        if claims:
            sections.append("Recent active claims:\n" + claims)

        lenses = self._active_lenses()
        if lenses:
            sections.append("Active lenses:\n" + lenses)

        chats = await self._recent_sessions()
        if chats:
            sections.append("Recent chats:\n" + chats)

        existing = await self._existing_automations()
        if existing:
            sections.append("Existing automations (do NOT duplicate):\n" + existing)

        excluded = await self._excluded_signatures()
        if excluded:
            sections.append("Previously dismissed/accepted (do NOT re-suggest):\n" + excluded)

        if not sections:
            return "No signal available."
        return "\n\n".join(sections)

    async def _memory_subjects(self) -> str:
        try:
            rows = await self.memory.distinct_subjects(_USER_SCOPE)
        except Exception as e:
            _logger.debug("gather distinct_subjects failed: %s", e)
            return ""
        return "\n".join(f"- {subject} ({count})" for subject, count in rows[:_MAX_SUBJECTS])

    async def _recent_claims(self) -> str:
        try:
            items = await self.memory.query(scope=_USER_SCOPE, limit=_MAX_CLAIMS)
        except Exception as e:
            _logger.debug("gather query claims failed: %s", e)
            return ""
        return "\n".join(f"- {item.content}" for item in items)

    def _active_lenses(self) -> str:
        try:
            lenses = self.memory.lens_files.list()
        except Exception as e:
            _logger.debug("gather lenses failed: %s", e)
            return ""
        return "\n".join(f"- {lens.name}" for lens in lenses)

    async def _recent_sessions(self) -> str:
        try:
            rows = await self.sessions.list_sessions(limit=_MAX_SESSIONS)
        except Exception as e:
            _logger.debug("gather sessions failed: %s", e)
            return ""
        return "\n".join(f"- {row['name']}" for row in rows if row.get("name"))

    async def _existing_automations(self) -> str:
        try:
            automations = await self.automations.list_all()
        except Exception as e:
            _logger.debug("gather existing automations failed: %s", e)
            return ""
        return "\n".join(f"- {a.name} — {a.description}" for a in automations)

    async def _excluded_signatures(self) -> str:
        try:
            signatures = await self.automations.list_excluded_signatures()
        except Exception as e:
            _logger.debug("gather excluded signatures failed: %s", e)
            return ""
        return "\n".join(f"- {sig}" for sig in signatures)
