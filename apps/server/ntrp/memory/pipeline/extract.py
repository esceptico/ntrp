"""Extract (CONTRACTS.md §6) — atomize + ground, store-free.

Turns one admitted exchange into atomic, self-contained ``ClaimCandidate``s,
coreference resolved inline, each grounded in exactly one cited turn. Decides
nothing about worth (Admit did) and resolves nothing against the store
(Reconcile does). NO store dependency — this is what lets a replay corpus run
Extract+Reconcile deterministically over history.

Subject identity is the model's job, not a regex's. The extractor already
resolves coreference for ``content``, so it ALSO emits the resolved subject as a
structured field (``canonical_subject``) plus every surface form it saw
(``subject_surfaces``). There is no proper-noun regex and no stopword set here:
the only guards are pure categorical checks (empty content, unresolvable turn id,
model-flagged-ungrounded, empty subject) — no lexical/rule heuristic decides what
a claim is about or whether a name is faithful (the model's ``grounded`` flag,
backed by re-groundable ``source_refs``, owns faithfulness).

Cost: exactly one cheap LLM call per admitted exchange; all guards are pure CPU.
"""

from ntrp.llm.base import CompletionClient
from ntrp.memory.models import Provenance
from ntrp.memory.pipeline.prompts_extract import (
    EXTRACT_SYSTEM,
    EXTRACT_USER_TEMPLATE,
    ExtractOutput,
)
from ntrp.memory.pipeline.types import (
    AdmitResult,
    ClaimCandidate,
    DroppedSpan,
    ExtractResult,
    RawExchange,
    Verdict,
)

_PROVENANCE_BY_NAME: dict[str, Provenance] = {
    "user_authored": Provenance.USER_AUTHORED,
    "recorded": Provenance.RECORDED,
    "inferred": Provenance.INFERRED,
    "external": Provenance.EXTERNAL,
}

# Default provenance when the model emits an unrecognized label. RECORDED is the
# neutral floor for an agent-observed fact; never silently up-rank to authored.
_PROVENANCE_DEFAULT = Provenance.RECORDED


class Extractor:
    def __init__(self, cheap_llm: CompletionClient):
        self._llm = cheap_llm

    async def extract(self, admitted: AdmitResult, *, model: str) -> ExtractResult:
        if admitted.verdict is not Verdict.ADMIT:
            return ExtractResult(candidates=[], dropped=[])

        unit = admitted.unit
        by_turn: dict[str, RawExchange] = {ex.turn_id: ex for ex in unit.exchanges}
        if not by_turn:
            return ExtractResult(candidates=[], dropped=[])

        messages = self._build_prompt(admitted)
        parsed = await self._call(messages, model=model)

        candidates: list[ClaimCandidate] = []
        dropped: list[DroppedSpan] = []

        for claim in parsed.claims:
            content = (claim.content or "").strip()
            turn_id = (claim.source_turn_id or "").strip()
            exchange = by_turn.get(turn_id)

            # Guard 1: empty content / unresolvable turn id.
            if not content:
                continue
            if exchange is None:
                dropped.append(
                    DroppedSpan(
                        turn_id=turn_id or None,
                        attempted_content=content,
                        reason="evidence_missing",
                    )
                )
                continue

            # Guard 2: model flagged the claim as not fully grounded.
            if not claim.grounded:
                dropped.append(
                    DroppedSpan(
                        turn_id=turn_id,
                        attempted_content=content,
                        reason="grounded_false",
                    )
                )
                continue

            # Guard 3: the model must have resolved a canonical subject. Pure
            # empty-field check — no lexical/regex rule decides identity here.
            canonical_subject = (claim.canonical_subject or "").strip()
            if not canonical_subject:
                dropped.append(
                    DroppedSpan(
                        turn_id=turn_id,
                        attempted_content=content,
                        reason="subject_unresolved",
                    )
                )
                continue

            surfaces = [s.strip() for s in (claim.subject_surfaces or []) if s and s.strip()]
            candidates.append(
                ClaimCandidate(
                    content=content,
                    source_refs=[exchange.source_ref],
                    provenance=_PROVENANCE_BY_NAME.get(
                        (claim.provenance or "").strip().lower(), _PROVENANCE_DEFAULT
                    ),
                    scope=unit.scope,
                    canonical_subject=canonical_subject,
                    subject_surfaces=surfaces,
                )
            )

        return ExtractResult(candidates=candidates, dropped=dropped)

    # -- internals ---------------------------------------------------

    def _build_prompt(self, admitted: AdmitResult) -> list[dict]:
        unit = admitted.unit
        turns = "\n".join(
            f"[turn_id={ex.turn_id}] {ex.text}" for ex in unit.exchanges
        )
        residual = (admitted.residual or "").strip() or "(none; weigh all turns)"
        user = EXTRACT_USER_TEMPLATE.format(
            scope_label=self._scope_label(unit.scope),
            residual=residual,
            turns=turns,
        )
        return [
            {"role": "system", "content": EXTRACT_SYSTEM},
            {"role": "user", "content": user},
        ]

    async def _call(self, messages: list[dict], *, model: str) -> ExtractOutput:
        """The single cheap LLM call (the one LLM seam in this stage).

        Contract (CONTRACTS §6/§13): one cheap structured-output call over
        ``ExtractOutput``. Uses the frozen ``CompletionClient.completion`` API
        with ``response_format`` (same convention as ``core/naming.py``): the
        provider returns a JSON string in ``choices[0].message.content`` which
        is parsed with ``model_validate_json``. On any client/parse failure
        Extract yields nothing rather than emitting ungrounded claims —
        drop-on-doubt; evidence is re-extractable from immutable raw.
        """
        try:
            response = await self._llm.completion(
                messages=messages,
                model=model,
                response_format=ExtractOutput,
            )
        except Exception:
            return ExtractOutput(claims=[])
        return self._parse_response(response)

    @staticmethod
    def _parse_response(response) -> ExtractOutput:
        choices = getattr(response, "choices", None)
        if not choices:
            return ExtractOutput(claims=[])
        content = choices[0].message.content
        if not content:
            return ExtractOutput(claims=[])
        try:
            return ExtractOutput.model_validate_json(content)
        except Exception:
            return ExtractOutput(claims=[])

    @staticmethod
    def _scope_label(scope) -> str:
        return f"{scope.kind}:{scope.key}" if scope.key else str(scope.kind)
