"""Structured-output schemas + rubric for record CONSOLIDATE/LINT.

Adapted from the old claim-pipeline `prompts_consolidate.py` to the flat
RecordStore: no subject/provenance/corroboration/feedback/validity/edge fields —
a record is just {id, text, kind, last_confirmed_at, pinned}. The judge proposes
only three ops over a recalled neighborhood; it never invents facts, never raises
trust, and never touches a pinned record.
"""

from pydantic import BaseModel, Field

# Prompt-cacheable prefix. The bar to act is HIGH, NOOP is the safe default, and
# a pinned record is never merged or invalidated away.
LINT_RUBRIC = """You are CONSOLIDATING a small slice of a personal memory of atomic RECORDS.

Consolidation is not deduplication. Most records are raw OBSERVATIONS (kind 'note').
Your job is to integrate them into a SMALL, CLEAN body of coherent knowledge: fold
together what is really one thing, name it by what it IS, and clear out what's stale.

You are shown a NEIGHBORHOOD of records (id, text, kind, last_confirmed_at, pinned).
Propose ONLY these operations:

- merge: two or more records that are observations, restatements, refinements, or
  accumulating evidence of the SAME underlying fact / preference / behavior / pattern.
  Integrate them into ONE coherent, self-contained statement (`merged_text`) and
  collapse the rest into it. List EVERY member id. Set `kind` to what the integrated
  statement IS by function:
    'fact'       — a stable standing fact about the user or their world,
    'preference' — a recurring like/dislike/habit/pattern,
    'action'     — a workflow / procedure / how-to,
    'note'       — leave raw only if it genuinely rises to none of the above.
- retype: a SINGLE record whose kind is wrong — most often a raw 'note' that actually
  states a standing fact, preference, or workflow. Give its id and the correct kind.
  This is how raw observations become real, typed knowledge.
- invalidate: a record is stale (no longer true) or contradicted by a newer record
  shown here. Give the id and, when a newer record supersedes it, contradicted_by.
- drop_orphan: a record that carries no standalone value and whose evidence is gone
  (no provenance source) — a stray fragment.
- noop: when records are unrelated, or you are unsure.

Hard rules:
- INTEGRATE aggressively within one topic, but NEVER merge records that carry
  DISTINCT facts — even on the same subject. A false merge that blends two different
  facts poisons the memory. When two records say genuinely different things, keep both.
- The integrated `merged_text` must be fully supported by its members. NEVER invent
  facts, dates, or numbers, and never lose a distinct fact a member carried.
- NEVER merge, invalidate, drop, or retype a record whose "pinned" is true.
- A merge needs at least two member ids. Use only ids that appear in the neighborhood.

Output strictly as the requested JSON."""


class MergeOp(BaseModel):
    op: str = Field(default="merge", description="literal 'merge'")
    member_ids: list[str] = Field(description="ids of the records that are one thing, to integrate")
    merged_text: str | None = Field(
        default=None, description="the integrated, self-contained wording for the survivor"
    )
    kind: str | None = Field(
        default=None, description="function-type of the integrated statement: fact|preference|action|note"
    )
    reason: str = ""


class RetypeOp(BaseModel):
    op: str = Field(default="retype", description="literal 'retype'")
    record_id: str
    kind: str = Field(description="correct function-type: fact|preference|action|note")
    reason: str = ""


class InvalidateOp(BaseModel):
    op: str = Field(default="invalidate", description="literal 'invalidate'")
    record_id: str
    contradicted_by: str | None = Field(
        default=None,
        description="id of the newer record that contradicts/supersedes this one, if any",
    )
    reason: str = ""


class DropOrphanOp(BaseModel):
    op: str = Field(default="drop_orphan", description="literal 'drop_orphan'")
    record_id: str
    reason: str = ""


class LintOps(BaseModel):
    merges: list[MergeOp] = Field(default_factory=list)
    retypes: list[RetypeOp] = Field(default_factory=list)
    invalidations: list[InvalidateOp] = Field(default_factory=list)
    orphans: list[DropOrphanOp] = Field(default_factory=list)


LABEL_HYGIENE_RUBRIC = """You are canonicalizing the LABEL vocabulary of a personal memory.

Labels are short open-vocabulary names the curator attaches to records — referents
("Dex", "MATS") and categories ("health", "open loops") alike. You are shown the
whole vocabulary as `label: active-record-count` lines. Propose a rename ONLY for
labels that are clearly the SAME label spelled differently: case variants,
singular/plural, or trivial rephrasings of one name ("dex" / "Dex memory").
Fold the variant (`old`) into the canonical name (`new`) — prefer the more
popular spelling, break ties toward the shorter, properly-cased name.

Hard rules:
- NEVER fold two labels that name genuinely different things, even when related
  ("health" and "medication" stay separate).
- When unsure, leave both. An empty list is the normal answer.

Output strictly as the requested JSON."""


class LabelRenameOp(BaseModel):
    old: str = Field(description="the variant spelling to fold away")
    new: str = Field(description="the canonical label name to fold it into")
    reason: str = ""


class LabelOps(BaseModel):
    renames: list[LabelRenameOp] = Field(default_factory=list)
