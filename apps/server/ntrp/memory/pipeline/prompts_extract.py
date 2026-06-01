"""Extract stage rubric + structured-output schema (CONTRACTS §6).

CONTRACTS §13 nominally puts every stage's prompts in a single ``prompts.py``;
the parallel build instead settled on per-stage prompt modules
(``prompts_capture.py``, ``prompts_retrieve.py``, ``prompts_reconcile.py``) to
avoid write collisions on the shared file. Extract follows that de-facto
pattern. (Contract deviation noted, not freelanced — see the build report.)
"""

from pydantic import BaseModel, Field

EXTRACT_SYSTEM = """You extract atomic, self-contained claims from a conversation segment.

RULES
- One fact per claim. Never merge two facts into one claim. Never split one fact.
- Resolve every pronoun and reference inline so each claim stands alone WITHOUT \
the surrounding turns (e.g. "User prefers dark mode", not "He prefers it").
- Do not invent facts. Only state what is asserted in the cited turn.
- Each claim must cite the single turn id it is grounded in (source_turn_id).

FAITHFULNESS
- Set grounded=true ONLY if every token of the claim, including any pronoun \
antecedent you resolved AND the subject you canonicalized, is recoverable from \
the cited turn alone (the speaker's own identity may come from the scope context).
- If you had to guess an antecedent, invent a name absent from the turn, infer \
beyond the text, or stitch context from another turn, set grounded=false.

PROVENANCE (pick the coarse category, do not over-think it)
- user_authored: the user explicitly stated or corrected this fact.
- recorded: an agent/tool observed or reported this fact.
- inferred: you synthesized this by spanning multiple turns.
- external: sourced from an external document/system quoted in the turn.

SUBJECT
- The claim is about exactly one subject. canonical_subject is its stable, \
fully-resolved real-world referent — the name you'd use to look this entity up \
every time, regardless of how this turn happened to refer to it. Normalize it so \
the SAME referent always gets the SAME string.
- If the turn says "I"/"me"/"my"/"the user" or otherwise refers to the \
assistant's principal, resolve canonical_subject to that person's canonical name \
when the scope context makes it known; otherwise use "the user".
- Two surface forms denoting the same referent in this segment MUST get the same \
canonical_subject.
- NEVER emit a pronoun, deictic, or role-relative phrase as canonical_subject \
("he", "it", "the manager" are forbidden as the canonical name).
- List every surface form you actually saw for this subject in the cited turn(s) \
in subject_surfaces (e.g. ["I", "me", "Timur"]). It is recall fuel and alias \
evidence only — it decides nothing.

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
        description="the stable, fully-resolved real-world referent this claim is "
        "about — the name you'd use to look this entity up every time, regardless "
        "of how this turn referred to it. Never a pronoun, role-relative phrase, "
        "or deixis."
    )
    subject_surfaces: list[str] = Field(
        default_factory=list,
        description="every surface form for THIS subject seen in the cited turn(s) "
        "(e.g. ['I','me','Timur']) — recall fuel and alias evidence only.",
    )
    grounded: bool = Field(description="true only if fully recoverable from the cited turn")


class ExtractOutput(BaseModel):
    claims: list[ExtractedClaim] = Field(default_factory=list)
