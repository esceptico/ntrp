"""Stage rubrics and structured-output schemas for the pipeline (CONTRACTS §5-9).

Each stage owns its own section here. Other stages append their rubrics/schemas
alongside without editing another stage's section.
"""

from pydantic import BaseModel, Field

# =====================================================================
# Admit (CONTRACTS §5)
# =====================================================================

# Prompt-cached prefix: the rubric is stable across calls. The A-MAC five
# factors are weighed as QUESTIONS, never scored; the predictive-IB framing
# admits only the part memory could NOT predict; the hard bar is verbatim.
ADMIT_SYSTEM = """You are the admission gate of a personal long-term memory system.

Your job: decide whether an exchange contains anything WORTH durably remembering
that memory does NOT already know. You are shown the exchange and the nearest
existing claims memory already holds in this scope.

Weigh these factors as questions (never assign a score):
- Future utility: would recalling this later change a decision or save work?
- Factual confidence: is this a stable assertion about the user or the world?
- Semantic novelty: does memory already predict this from the claims shown?
- Temporal recency: is this a fresh state that supersedes what memory holds?
- Content-type prior: durable facts/preferences/decisions over transient chatter.

Apply the predictive-information principle: admit ONLY the part memory could NOT
predict. If every assertion in the exchange is already implied by the claims
shown, there is nothing to admit.

THE HARD BAR (do not soften it):
Most exchanges admit NOTHING. Operational runs, the agent doing its job, and
restating known facts all REJECT. Never turn one short debugging or task segment
into a durable fact.

Return:
- predictable_from_memory: true if the claims shown already cover everything
  asserted here (then nothing new to admit).
- surprising_residual: the specific NEW assertion memory could not predict, in
  one short phrase. Empty string when predictable_from_memory is true. This is a
  seed that narrows later extraction -- it is never stored as a claim.
- reason: one line explaining the call, for the audit trail."""

# Stronger default-REJECT framing appended for AUTOMATION-role units.
ADMIT_AUTOMATION_SUFFIX = """

This exchange is an AUTOMATION run. The agent executing its routine is NOT a
memorable event. Default strongly to REJECT: admit only a genuinely new, durable
fact about the user or world that surfaced during the run -- never the run's own
mechanics, status, or progress."""


class AdmitDecision(BaseModel):
    """Structured output of the single Admit judgment call (CONTRACTS §5.4).

    No score, no confidence float -- only the categorical judgment plus a
    one-line audit reason and the surprising residual seed.
    """

    predictable_from_memory: bool = Field(
        description="True if the claims shown already cover everything asserted in the exchange."
    )
    surprising_residual: str = Field(
        default="",
        description="The new assertion memory could not predict, one short phrase; empty if predictable.",
    )
    reason: str = Field(description="One line explaining the verdict, for the audit trail.")


def render_admit_user(exchange_text: str, candidate_contents: list[str]) -> str:
    """Dynamic tail: the trimmed exchange beside the recalled claim contents."""
    if candidate_contents:
        recalled = "\n".join(f"- {c}" for c in candidate_contents)
    else:
        recalled = "(memory holds no related claims in this scope)"
    return (
        f"EXCHANGE:\n{exchange_text}\n\n"
        f"WHAT MEMORY ALREADY KNOWS (nearest existing claims):\n{recalled}\n\n"
        "Decide whether this exchange asserts anything new and worth keeping."
    )


# =====================================================================
# Extract (CONTRACTS §6)
# =====================================================================

EXTRACT_SYSTEM = """You extract atomic, self-contained claims from a conversation segment.

RULES
- One fact per claim. Never merge two facts into one claim. Never split one fact.
- Resolve every pronoun and reference inline so each claim stands alone WITHOUT \
the surrounding turns (e.g. "User prefers dark mode", not "He prefers it").
- Do not invent facts. Only state what is asserted in the cited turn.
- Each claim must cite the single turn id it is grounded in (source_turn_id).

FAITHFULNESS
- Set grounded=true ONLY if every token of the claim, including any pronoun \
antecedent you resolved, is recoverable from the cited turn alone.
- If you had to guess an antecedent, infer beyond the text, or stitch context \
from another turn, set grounded=false.

PROVENANCE (pick the coarse category, do not over-think it)
- user_authored: the user explicitly stated or corrected this fact.
- recorded: an agent/tool observed or reported this fact.
- inferred: you synthesized this by spanning multiple turns.
- external: sourced from an external document/system quoted in the turn.

SUBJECT
- The claim is about exactly one subject. canonical_subject = its stable resolved \
name, normalized so the same referent always gets the same string. If the turn says \
"I"/"me"/"the user" or addresses the assistant's principal, resolve it to that \
person's canonical name when known from the scope context, else "the user". Two \
surface forms denoting the same referent in this segment MUST get the same \
canonical_subject. Never emit a pronoun or role-relative phrase as canonical_subject.
- List every surface form you saw for this subject in subject_surfaces.

Output ONLY claims that carry durable, self-contained meaning. Prefer dropping a \
shaky claim over emitting an ungrounded one. Return a JSON object matching the schema."""


EXTRACT_USER_TEMPLATE = """SCOPE (context only, do not restate): {scope_label}

NOVELTY SEED (focus extraction here; the rest is likely already known):
{residual}

ADMITTED TURNS (each tagged with a stable turn_id):
{turns}

Extract the atomic, self-contained claims."""


class ExtractedClaim(BaseModel):
    content: str = Field(description="atomic, self-contained, coreference resolved inline")
    source_turn_id: str = Field(description="the single turn_id this claim is grounded in")
    provenance: str = Field(description="one of: user_authored | recorded | inferred | external")
    canonical_subject: str = Field(
        description="the stable, fully-resolved real-world referent this claim is about; "
        "never a pronoun, role-relative phrase, or deixis."
    )
    subject_surfaces: list[str] = Field(
        default_factory=list,
        description="every surface form for THIS subject seen in the cited turn(s); "
        "recall fuel and alias evidence only.",
    )
    grounded: bool = Field(description="true only if fully recoverable from the cited turn")


class ExtractOutput(BaseModel):
    claims: list[ExtractedClaim] = Field(default_factory=list)
