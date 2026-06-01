"""Reconcile-stage rubrics + structured-output schemas (CONTRACTS §7, §13).

Per-stage prompt module, mirroring the prompts_capture/prompts_retrieve split the
other stages use. The Reconcile component imports its prompts only from here so
the shared prompts.py (Admit/Extract sections) is never contended.
"""

from pydantic import BaseModel, Field

# --- Reconcile Phase 2: subject resolution --------------------------

SUBJECT_RESOLUTION_SYSTEM = """\
You name the canonical subject a new fact is about, in a personal knowledge base.

Subjects are not stored as records — a subject is just a stable string attached to each
claim (its `canonical_subject`). Two claims are about the same referent iff they carry
the same canonical_subject string. Your job: given a new fact's proposed SUBJECT and
CONTENT, plus a list of EXISTING canonical subjects already used by nearby claims, return
the canonical subject string to assign this fact.

Decide one of:
- MATCH: this fact is about the SAME real-world referent as one of the existing subjects.
  Return that existing canonical_subject string VERBATIM so the claims group together.
- NEW: none of the existing subjects is the same referent. Return the proposed SUBJECT
  (lightly normalized) as the new canonical subject.

Rules:
- Match only on identity, never on mere topical similarity. "my therapist" and "my
  doctor" are different people unless context proves they are one.
- When genuinely uncertain between a match and a new subject, choose NEW. A wrong NEW is
  cheaply repaired by background cleanup; a wrong MATCH poisons a profile.
- canonical_subject MUST be copied verbatim from the EXISTING list when MATCH; otherwise
  return the new subject string. Never return an id.
"""


class SubjectResolution(BaseModel):
    decision: str = Field(description='"MATCH" or "NEW"')
    canonical_subject: str = Field(
        description="the subject string to assign: an existing one verbatim (MATCH) or the new subject (NEW)"
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


# --- Lens membership (LLooM multiple-choice) — §4.1, shares the loop's home --

MEMBERSHIP_JUDGE_SYSTEM = """\
You decide, for each numbered ITEM, whether it BELONGS to a lens — a saved view over a
personal knowledge base defined ONLY by its membership CRITERION written in natural
language. This is a multiple-choice judgment, one vote per item, judged solely against
the criterion as written.

You are given the lens NAME, its membership CRITERION, a short PAGE_GIST for
context, an optional list of NEGATIVE_EXAMPLES (items the user previously rejected from
this lens — read them as examples of what does NOT belong, never as a keyword filter),
and a NUMBERED list of ITEMS.

For each item choose exactly one decision:
- in: the item clearly satisfies the criterion as written.
- out: the item does not satisfy the criterion. This is the default.
- defer: a genuinely close call you cannot settle confidently; a stronger judge will
  re-decide it.

Rules:
- Judge ONLY against the criterion as written. Topical adjacency is not membership: an
  item that is merely related to the lens's theme is `out` unless the criterion actually
  covers it.
- Bias to `out` under doubt. Absence of an explicit reason to include is `out`, not
  `defer`. Use `defer` sparingly, only when the item could plausibly read either way.
- Treat each NEGATIVE_EXAMPLE as a worked example of an `out` verdict for similar items.
- Never invent facts. Reason only over the item content shown.
- Return one vote per item, each carrying the item's index verbatim from the list.
"""


class MembershipVote(BaseModel):
    item_index: int = Field(description="index into the ITEMS list this vote decides")
    decision: str = Field(description='"in" | "out" | "defer"')
    rationale: str = ""


class MembershipBatch(BaseModel):
    votes: list[MembershipVote] = Field(default_factory=list)
