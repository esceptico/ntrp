from __future__ import annotations

import json
from dataclasses import dataclass, field
from re import findall
from typing import Any

from pydantic import BaseModel, Field


@dataclass(slots=True)
class EpisodeContext:
    """Minimal shape the boundary classifier needs about the current open episode.

    Replaces the legacy KnowledgeObject coupling; the chat connector builds one
    of these from the episode buffer.
    """

    title: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


class EpisodeBoundaryDecision(BaseModel):
    continue_current: bool = True
    close_current: bool = False
    open_new: bool = False
    boundary_type: str | None = None
    episode_title: str | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)


class EpisodeMemoryCandidate(BaseModel):
    object_type: str = Field(description="fact, lesson, artifact, or action_candidate")
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=2000)
    kind: str = "episode_close"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_quote: str | None = Field(default=None, max_length=1000)


class EpisodeMemoryExtraction(BaseModel):
    memories: list[EpisodeMemoryCandidate] = Field(default_factory=list, max_length=8)


_EXPLICIT_SWITCH_MARKERS = (
    "new topic",
    "switch topic",
    "switching topic",
    "forget that",
    "separate task",
    "different task",
    "now do ",
    "next do ",
    "let's move to",
    "lets move to",
    "/goal ",
)

_COMPLETION_MARKERS = (
    "done",
    "completed",
    "complete",
    "fixed",
    "resolved",
    "implemented",
    "shipped",
    "verified",
    "tests pass",
    "all checks passed",
    "goal complete",
    "that worked",
)

_FAILURE_RESOLVED_MARKERS = (
    "error resolved",
    "bug fixed",
    "failure resolved",
    "issue resolved",
)

_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "into",
    "have",
    "your",
    "you",
    "are",
    "was",
    "were",
    "will",
    "would",
    "should",
    "can",
    "could",
    "task",
    "work",
}


def _normalized(text: str) -> str:
    return " ".join(text.lower().split())


def _terms(text: str) -> set[str]:
    return {term for term in findall(r"[a-zA-Z0-9_]+", text.lower()) if len(term) > 2 and term not in _STOPWORDS}


def _first_line_title(text: str) -> str:
    line = text.strip().splitlines()[0] if text.strip() else "Untitled memory episode"
    line = line.removeprefix("Result:").strip()
    if len(line) > 90:
        line = f"{line[:87].rstrip()}..."
    return f"Episode: {line}"


def _fallback_safe(decision: EpisodeBoundaryDecision, fallback: EpisodeBoundaryDecision) -> EpisodeBoundaryDecision:
    """Prevent a weak/empty model answer from dropping obvious deterministic signals."""
    if fallback.close_current and fallback.confidence >= decision.confidence:
        return fallback
    if decision.close_current and decision.open_new and not decision.episode_title:
        decision.episode_title = fallback.episode_title
    return decision


class EpisodeBoundaryClassifier:
    """Small deterministic boundary policy used when no model classifier is wired.

    This intentionally does not split on arbitrary turn/run counts. It only emits
    a boundary for explicit switches or outcome/completion language; otherwise it
    keeps appending evidence to the current open episode.
    """

    def decide(
        self,
        *,
        current_episode: EpisodeContext | None,
        event_text: str,
        idle_seconds: int | None = None,
    ) -> EpisodeBoundaryDecision:
        text = _normalized(event_text)
        evidence: list[str] = []

        if current_episode is None or current_episode.metadata.get("episode_status") != "open":
            completion_marker = next((marker for marker in _COMPLETION_MARKERS if marker in text), None)
            if completion_marker:
                return EpisodeBoundaryDecision(
                    continue_current=True,
                    close_current=True,
                    open_new=True,
                    boundary_type="task_completed",
                    episode_title=_first_line_title(event_text),
                    confidence=0.72,
                    evidence=["No open memory episode exists.", f"Completion marker: {completion_marker!r}."],
                )
            failure_marker = next((marker for marker in _FAILURE_RESOLVED_MARKERS if marker in text), None)
            if failure_marker:
                return EpisodeBoundaryDecision(
                    continue_current=True,
                    close_current=True,
                    open_new=True,
                    boundary_type="failure_resolved",
                    episode_title=_first_line_title(event_text),
                    confidence=0.76,
                    evidence=["No open memory episode exists.", f"Failure-resolution marker: {failure_marker!r}."],
                )
            return EpisodeBoundaryDecision(
                continue_current=False,
                open_new=True,
                boundary_type="no_open_episode",
                episode_title=_first_line_title(event_text),
                confidence=0.7,
                evidence=["No open memory episode exists."],
            )

        switch_marker = next((marker for marker in _EXPLICIT_SWITCH_MARKERS if marker in text), None)
        if switch_marker:
            return EpisodeBoundaryDecision(
                continue_current=False,
                close_current=True,
                open_new=True,
                boundary_type="explicit_switch",
                episode_title=_first_line_title(event_text),
                confidence=0.82,
                evidence=[f"Explicit switch marker: {switch_marker!r}."],
            )

        completion_marker = next((marker for marker in _COMPLETION_MARKERS if marker in text), None)
        if completion_marker:
            evidence.append(f"Completion marker: {completion_marker!r}.")
            return EpisodeBoundaryDecision(
                continue_current=True,
                close_current=True,
                open_new=False,
                boundary_type="task_completed",
                confidence=0.72,
                evidence=evidence,
            )

        failure_marker = next((marker for marker in _FAILURE_RESOLVED_MARKERS if marker in text), None)
        if failure_marker:
            return EpisodeBoundaryDecision(
                continue_current=True,
                close_current=True,
                open_new=False,
                boundary_type="failure_resolved",
                confidence=0.76,
                evidence=[f"Failure-resolution marker: {failure_marker!r}."],
            )

        current_terms = _terms(f"{current_episode.title}\n{current_episode.text}")
        event_terms = _terms(event_text)
        overlap = current_terms & event_terms
        if overlap:
            evidence.append(f"Shared task terms: {', '.join(sorted(overlap)[:5])}.")
        elif idle_seconds is not None:
            evidence.append("Idle gap alone is not treated as a semantic boundary.")

        return EpisodeBoundaryDecision(
            continue_current=True,
            close_current=False,
            open_new=False,
            confidence=0.6 if overlap else 0.45,
            evidence=evidence or ["No reliable boundary signal."],
        )


class ModelBackedEpisodeBoundaryClassifier(EpisodeBoundaryClassifier):
    """LLM boundary classifier with deterministic fallback.

    The model decides semantic episode boundaries. The fallback guards obvious
    switch/completion cases and keeps offline tests/provider outages stable.
    """

    def __init__(self, model: str, *, fallback: EpisodeBoundaryClassifier | None = None, max_tokens: int = 700):
        self.model = model
        self.fallback = fallback or EpisodeBoundaryClassifier()
        self.max_tokens = max_tokens

    async def decide(
        self,
        *,
        current_episode: EpisodeContext | None,
        event_text: str,
        idle_seconds: int | None = None,
    ) -> EpisodeBoundaryDecision:
        fallback = self.fallback.decide(
            current_episode=current_episode,
            event_text=event_text,
            idle_seconds=idle_seconds,
        )
        if current_episode is None:
            return fallback

        from ntrp.llm.router import get_completion_client

        payload = {
            "current_episode": {
                "title": current_episode.title,
                "summary": current_episode.text[-4000:],
                "metadata": current_episode.metadata,
            },
            "new_event": event_text[-4000:],
            "idle_seconds": idle_seconds,
            "fallback_decision": fallback.model_dump(),
        }
        try:
            response = await get_completion_client(self.model).completion(
                model=self.model,
                temperature=0,
                max_tokens=self.max_tokens,
                response_format=EpisodeBoundaryDecision,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Decide whether a personal-assistant memory episode should continue, close, or split. "
                            "An episode is a coherent task/event/topic segment spanning multiple turns/runs. "
                            "Never split solely because a run completed, a turn count changed, or an idle gap exists. "
                            "Use boundaries only for semantic signals: explicit topic switch, task completion, decision, "
                            "artifact delivered, failure/correction resolved, or source-native close. Return strict JSON."
                        ),
                    },
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
            )
            content = response.choices[0].message.content if response.choices else None
            if not content:
                return fallback
            decision = EpisodeBoundaryDecision.model_validate_json(content)
        except Exception:
            return fallback
        return _fallback_safe(decision, fallback)
