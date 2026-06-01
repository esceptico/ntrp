"""Admit -- the one cheap gate that governs volume (CONTRACTS §5).

Retrieval-grounded surprise test: recall first, then judge the residual against
what memory already knows. Most exchanges admit nothing, so most stop here.

Cost ceiling: exactly ONE cheap LLM call per surviving exchange. The correction
short-circuit and the free-rejection tier pull the amortized cost below 1.
Store usage is strictly read-only.
"""

from ntrp.embedder import Embedder
from ntrp.llm.base import CompletionClient
from ntrp.logging import get_logger
from ntrp.memory.models import MemoryItem, Status, now_iso
from ntrp.memory.pipeline.prompts import (
    ADMIT_AUTOMATION_SUFFIX,
    ADMIT_SYSTEM,
    AdmitDecision,
    render_admit_user,
)
from ntrp.memory.pipeline.types import (
    AdmitResult,
    CaptureUnit,
    ExchangeRole,
    Verdict,
)
from ntrp.memory.store import MemoryStore

_logger = get_logger(__name__)

# Routing heuristics only -- they decide WHO the model judges, never the verdict.
_RECALL_SEARCH_LIMIT = 8
_RECALL_QUERY_LIMIT = 12
_TRIVIAL_LENGTH_FLOOR = 12  # chars of meaningful content below which there is nothing to judge
_EXCHANGE_HEAD = 4000  # head/tail truncation budget for long dumps
_EXCHANGE_TAIL = 2000


class AdmitGate:
    def __init__(self, store: MemoryStore, cheap_llm: CompletionClient, embed: Embedder, *, model: str):
        self.store = store
        self.cheap_llm = cheap_llm
        self.embed = embed
        self.model = model

    async def admit(self, unit: CaptureUnit) -> AdmitResult:
        text = self._unit_text(unit)

        # Step 1 -- correction short-circuit (0 LLM). Still recalls so candidates
        # flow downstream; skips the judgment call.
        if unit.forced:
            candidates = await self._recall(unit, text)
            return AdmitResult(
                verdict=Verdict.ADMIT,
                unit=unit,
                residual=text,
                reason="forced: correction/remember short-circuit",
                candidates=candidates,
                forced=True,
            )

        # Step 2 -- free-rejection tier (0 LLM). Definitionally empty content.
        empty_reason = self._free_rejection_reason(text)
        if empty_reason is not None:
            return AdmitResult(
                verdict=Verdict.REJECT,
                unit=unit,
                residual=None,
                reason=empty_reason,
                candidates=[],
                forced=False,
            )

        # Step 3 -- recall (0 LLM, store-only).
        candidates = await self._recall(unit, text)

        # Step 4 -- the one cheap call.
        decision = await self._judge(unit, text, candidates)
        biased_admit = not self.store.has_fts

        if decision is None:
            # Parse/LLM failure: bias toward ADMIT (false-reject of a new fact is
            # not recoverable; false-admit is).
            return AdmitResult(
                verdict=Verdict.ADMIT,
                unit=unit,
                residual=text,
                reason="judge unavailable -> biased ADMIT",
                candidates=candidates,
                forced=False,
            )

        admit = not decision.predictable_from_memory
        if biased_admit and decision.predictable_from_memory:
            # FTS down -> judged on thin context -> bias toward ADMIT.
            admit = True

        verdict = Verdict.ADMIT if admit else Verdict.REJECT
        residual = (decision.surprising_residual or text) if verdict is Verdict.ADMIT else None
        return AdmitResult(
            verdict=verdict,
            unit=unit,
            residual=residual,
            reason=decision.reason,
            candidates=candidates,
            forced=False,
        )

    # --- internals ---

    def _unit_text(self, unit: CaptureUnit) -> str:
        return "\n".join(ex.text for ex in unit.exchanges).strip()

    def _free_rejection_reason(self, text: str) -> str | None:
        """REJECT-without-a-call ONLY when the unit is definitionally empty
        (a length floor -- 'is there anything here at all').

        Single structural check: a trivial-length floor. NO content/keyword/
        prefix matching -- tool-status chatter, operational repeats, and known
        SOPs all flow to the judge, which rejects them (memory already holds them
        -> surprise ~= 0). Keeping what-to-remember a single LLM judgment, never a
        string list. (Cost on pure-tool turns is bounded structurally upstream at
        capture, by message-role, not by matching content here.)
        """
        stripped = text.strip()
        if len(stripped) < _TRIVIAL_LENGTH_FLOOR:
            return "free-reject: below trivial-length floor"
        return None

    async def _recall(self, unit: CaptureUnit, text: str) -> list[MemoryItem]:
        """Scope-correct recall of the incumbents the judgment is made against.

        search() is active-only and NOT scope-filtered, so its hits are
        intersected with a scoped query() id-set. When FTS is unavailable, fall
        back to the scoped query() pool alone (judge then biases toward ADMIT).
        """
        scoped = await self.store.query(
            scope=unit.scope,
            status=Status.ACTIVE,
            valid_at=now_iso(),
            limit=_RECALL_QUERY_LIMIT,
        )
        if not self.store.has_fts:
            return scoped

        scoped_ids = {item.id for item in scoped}
        hits = await self.store.search(text, limit=_RECALL_SEARCH_LIMIT)

        by_id: dict[str, MemoryItem] = {}
        for item in hits:
            if item.id in scoped_ids:
                by_id[item.id] = item
        # Seed with the scoped pool so judgment never starves when FTS misses.
        for item in scoped:
            by_id.setdefault(item.id, item)
        return list(by_id.values())

    async def _judge(
        self, unit: CaptureUnit, text: str, candidates: list[MemoryItem]
    ) -> AdmitDecision | None:
        """The single cheap call. Returns the parsed decision, or None on failure."""
        system = ADMIT_SYSTEM
        if unit.role is ExchangeRole.AUTOMATION:
            system = system + ADMIT_AUTOMATION_SUFFIX

        contents = [c.content for c in candidates]
        user = render_admit_user(self._trim(text), contents)

        try:
            response = await self.cheap_llm.completion(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                model=self.model,
                response_format=AdmitDecision,
            )
            content = response.choices[0].message.content
            if not content:
                return None
            return AdmitDecision.model_validate_json(content)
        except Exception as e:
            _logger.warning("admit judge failed: %s", e)
            return None

    def _trim(self, text: str) -> str:
        if len(text) <= _EXCHANGE_HEAD + _EXCHANGE_TAIL:
            return text
        return text[:_EXCHANGE_HEAD] + "\n...[truncated]...\n" + text[-_EXCHANGE_TAIL:]
