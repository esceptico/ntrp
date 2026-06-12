"""Structured-output schemas + rubrics for the dreamer's DERIVATION pass.

Three judgments (Derivation — spec.md §3-4):
  DREAM   — question-first derivation over a neighborhood (Generative Agents):
            salient questions, then conclusions the records JOINTLY imply,
            citing premises, typed by inference mode (Honcho).
  VERIFY  — reversed-framing check before commit (ADM): supported by ONLY the
            premises? already stated? non-trivial?
  REJUDGE — a derivation whose premise died: re-affirm / revise / retire
            against surviving premises + the superseding record (JTMS + AGM).
"""

from pydantic import BaseModel, Field

DREAM_RUBRIC = """You are the DREAMER of a personal memory of atomic RECORDS. You are shown a
NEIGHBORHOOD of related records (id -> text), some marked [inferred]. Your job is
INFERENCE, not summary: derive what these records JOINTLY imply that no record
already states.

Work question-first:
1. Ask yourself: what are the 1-3 most SALIENT QUESTIONS this neighborhood raises
   that the memory could answer but has not stated?
2. For each question, ONLY if some of these records together imply an answer,
   emit a candidate: the question, one atomic self-contained conclusion, the ids
   of the premise records it follows from, and the inference mode:
     "deduction" — the premises entail it,
     "induction" — a recurring pattern generalized from >=2 instances,
     "abduction" — the best available explanation (use sparingly).

Hard rules:
- The bar is HIGH. Most neighborhoods imply NOTHING new — return no candidates.
  Restatements, paraphrases, and summaries of a single record are NOT derivations.
- Use ONLY ids present in the neighborhood; a conclusion must cite >=1 premise
  (>=2 for induction). NEVER invent facts, dates, numbers, or ids.
- The conclusion must be self-contained (resolve names inline) and must say
  something a reader could not get by reading one premise alone.
- NEVER derive a conclusion matching a RETRACTED CONCLUSION listed under NOGOODS
  — those were judged wrong from these premises before.

Output strictly as the requested JSON."""


VERIFY_RUBRIC = """You are the SKEPTIC. A candidate inference was proposed from a personal memory.
You are shown ONLY its premise records, a set of EXISTING nearby records, and the
candidate conclusion. Judge it adversarially:

- supported: does the conclusion follow from ONLY these premises — no outside
  knowledge, no specifics (dates, numbers, names) the premises don't contain?
- duplicate_of: if an EXISTING record already states this conclusion (same
  meaning, any wording), give its id; else null.
- nontrivial: is it more than a restatement/paraphrase/summary of one premise?

Default to rejection when uncertain: a false inference poisons the memory; a
missed one costs nothing — the dreamer will see these records again.

Output strictly as the requested JSON."""


REJUDGE_RUBRIC = """You maintain a personal memory of atomic RECORDS. An INFERRED record's premise
was superseded or retired — the inference is now UNRESOLVED. You are shown: the
inferred record (with the question it answered), its DEAD premise(s), the
SUPERSEDING record(s) (what replaced them, when one exists), and its SURVIVING
premises plus nearby records. Decide its fate:

- REAFFIRM — the conclusion still holds, supported by LIVE records. Cite the
  live premise ids that now support it (they may include the superseding record).
- REVISE — the conclusion holds in corrected form. Give the corrected text and
  the live premise ids supporting it.
- RETIRE — the conclusion no longer holds (it depended on what changed). Give a
  one-line `why`.

Hard rules: never invent facts or ids; premises must be live record ids shown to
you; be conservative — REVISE only when the correction is clearly entailed.

Output strictly as the requested JSON."""


class DerivationCandidate(BaseModel):
    question: str
    conclusion: str
    premise_ids: list[str] = Field(description="neighborhood ids the conclusion follows from")
    mode: str = Field(description="deduction | induction | abduction")
    reason: str = ""


class DreamOps(BaseModel):
    candidates: list[DerivationCandidate] = Field(default_factory=list)


class VerifyVerdict(BaseModel):
    supported: bool
    duplicate_of: str | None = Field(
        default=None, description="id of an EXISTING record already stating this; null if none"
    )
    nontrivial: bool
    reason: str = ""


class RejudgeOp(BaseModel):
    op: str = Field(description="REAFFIRM | REVISE | RETIRE")
    text: str | None = Field(default=None, description="corrected conclusion (REVISE only)")
    premise_ids: list[str] = Field(
        default_factory=list, description="live premise ids (REAFFIRM/REVISE)"
    )
    why: str = ""
