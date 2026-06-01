"""Reconcile-stage rubrics + structured-output schemas (CONTRACTS §7, §13).

Per-stage prompt module, mirroring the prompts_capture/prompts_retrieve split the
other stages use. The Reconcile component imports its prompts only from here so
the shared prompts.py (Admit/Extract sections) is never contended.
"""

from pydantic import BaseModel, Field

# --- Reconcile Phase 2: subject resolution --------------------------

SUBJECT_RESOLUTION_SYSTEM = """\
You resolve which existing entity a new fact is about, in a personal knowledge base.

You are given a fully-resolved SUBJECT (the stable real-world referent the fact is
about, with coreference already resolved), the fact's CONTENT, and a numbered list of
CANDIDATE entity records (each an editable "lens" with a name, a membership criterion
listing known aliases, and a short gist).

Decide one of:
- MATCH <lens_id>: the subject is the SAME real-world referent as that candidate.
- NEW: none of the candidates is the same referent; this is a new entity.

Rules:
- Match only on identity, never on mere topical similarity. "my therapist" and "my
  doctor" are different people unless an alias says otherwise.
- When genuinely uncertain between a match and a new entity, choose NEW. A wrong NEW is
  cheaply repaired by background cleanup; a wrong MATCH poisons a profile.
- If you MATCH and the SUBJECT is a NEW alias not already in the candidate's criterion,
  return it in alias_to_add so future facts recall this entity directly.
- lens_id MUST be copied verbatim from one of the candidates shown. Never invent one.
"""


class SubjectResolution(BaseModel):
    decision: str = Field(description='"MATCH" or "NEW"')
    lens_id: str | None = Field(
        default=None, description="the matched candidate's lens_id, verbatim; null when NEW"
    )
    alias_to_add: str | None = Field(
        default=None, description="a new surface alias to append to the matched lens criterion"
    )
    reason: str = ""


# --- Reconcile Phase 4: batch reconcile per subject -----------------

BATCH_RECONCILE_SYSTEM = """\
You reconcile new atomic facts about ONE subject against that subject's existing
profile in a personal knowledge base. You decide, per new fact, exactly one operation.

You are given the subject's profile summary, a NUMBERED list of the subject's existing
claims (each with index, content, provenance, corroboration count, user feedback, and
validity start), and a NUMBERED list of NEW facts to reconcile.

For each new fact, choose one op:
- ADD: genuinely new information not represented by any existing claim.
- UPDATE: the new fact revises/refines an existing claim (same proposition, newer/better
  value). Set target_idx to the existing claim's index and merged_text to the successor.
- NOOP: the new fact restates an existing claim with no new information. Set target_idx.
- CONTRADICT: the new fact directly conflicts with an existing claim (cannot both be
  true). Set target_idx and merged_text to the new, corrected claim.

Rules:
- Bias to ADD under doubt. Only UPDATE/NOOP/CONTRADICT when you are confident the new
  fact concerns the SAME proposition as the targeted existing claim.
- target_idx MUST be an index from the numbered existing-claims list. Never a content id.
  Omit target_idx for ADD.
- Deduplicate among the NEW facts too: if two new facts say the same thing, ADD the
  first and NOOP the rest with no target_idx.
- A user-authored fact must never be suppressed as NOOP against an inferred claim; prefer
  UPDATE or ADD so the user's assertion is recorded.
- Set contested=true when the decision is genuinely close, or when UPDATE/CONTRADICT
  targets a high-trust claim (user-authored or highly corroborated) — these get a
  second, stronger review.
- Never invent facts. Reason only over the content shown.
"""


class ReconcileRow(BaseModel):
    claim_index: int = Field(description="index into the NEW facts list this row decides")
    op: str = Field(description='"add" | "update" | "noop" | "contradict"')
    target_idx: int | None = Field(
        default=None, description="index into the existing-claims list; required for non-ADD"
    )
    merged_text: str | None = Field(
        default=None, description="for UPDATE/CONTRADICT, the successor claim text"
    )
    contested: bool = False
    rationale: str = ""


class BatchReconcile(BaseModel):
    rows: list[ReconcileRow] = Field(default_factory=list)
