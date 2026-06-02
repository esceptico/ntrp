"""Structured-output schemas + rubric for Consolidate/Lint (§8).

Kept in its own module (mirroring prompts_capture.py / prompts_retrieve.py) so
the hot-path prompts.py stays focused. The processor proposes only the four ops
over a recalled neighborhood; it never invents facts and never raises trust.
"""

from pydantic import BaseModel, Field

# The rubric is a prompt-cacheable prefix. Wording is deliberately strict: the
# bar to act is high, NOOP is the safe default, trust may only be demoted, and a
# user-confirmed claim is never invalidated or merged away (only flagged).
LINT_RUBRIC = """You are health-checking a small slice of a personal knowledge base.

You are shown a NEIGHBORHOOD of atomic claims (each with an id, content, subject
(the person/thing the claim is ABOUT), provenance, corroboration count, feedback,
validity window, source-ref summary, and an edges note) within a single scope.
Propose ONLY these operations:

- merge: two or more claims state the SAME fact ABOUT THE SAME SUBJECT; collapse
  duplicates onto one survivor. List every member id; the processor picks the
  best-grounded survivor. Claims with DIFFERENT subjects are never the same fact —
  similar wording about two different people/things must NOT be merged.
- invalidate: a claim is stale (no longer true) or is contradicted by a newer,
  better-grounded claim shown here. Give the claim id and a one-line reason.
- drop_orphan: a claim whose evidence is gone (no source refs and no connecting
  edge) and that carries no standalone value.
- noop: when you are not sure. This is the default.

Hard rules:
- The bar to act is HIGH. When unsure, NOOP. False merges poison a profile;
  false invalidations lose facts. Prefer leaving claims alone.
- Reason ONLY over the claims shown. NEVER invent facts, dates, or numbers.
- NEVER raise trust. Merging or invalidating only removes from circulation.
- NEVER invalidate or merge away a claim whose feedback is "confirmed"
  (the user touched it). If such a claim conflicts with another, leave both and
  do not act.
- A claim is a duplicate of another ONLY if a careful reader would say they
  assert the identical fact. Related, adjacent, or refining claims are NOT
  duplicates — NOOP them.
- Two genuinely contradictory high-provenance claims are NOT yours to resolve.
  Do not pick a winner; leave both (the processor flags the contradiction).

Output strictly as the requested JSON. Use only ids that appear in the
neighborhood."""


class MergeOp(BaseModel):
    op: str = Field(default="merge", description="literal 'merge'")
    member_ids: list[str] = Field(description="ids of the duplicate claims to collapse")
    merged_text: str | None = Field(
        default=None, description="optional unified wording for the survivor"
    )
    reason: str = ""


class InvalidateOp(BaseModel):
    op: str = Field(default="invalidate", description="literal 'invalidate'")
    claim_id: str
    contradicted_by: str | None = Field(
        default=None,
        description="id of the newer claim that contradicts this one, if any",
    )
    reason: str = ""


class DropOrphanOp(BaseModel):
    op: str = Field(default="drop_orphan", description="literal 'drop_orphan'")
    claim_id: str
    reason: str = ""


class NoOp(BaseModel):
    op: str = Field(default="noop", description="literal 'noop'")
    reason: str = ""


class LintOps(BaseModel):
    merges: list[MergeOp] = Field(default_factory=list)
    invalidations: list[InvalidateOp] = Field(default_factory=list)
    orphans: list[DropOrphanOp] = Field(default_factory=list)
