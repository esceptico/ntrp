"""Extract stage rubric + structured-output schema (CONTRACTS §6).

CONTRACTS §13 nominally puts every stage's prompts in a single ``prompts.py``;
the parallel build instead settled on per-stage prompt modules
(``prompts_capture.py``, ``prompts_retrieve.py``, ``prompts_reconcile.py``) to
avoid write collisions on the shared file. Extract follows that de-facto
pattern. (Contract deviation noted, not freelanced — see the build report.)
"""

from pydantic import BaseModel, Field

EXTRACT_SYSTEM = """You extract atomic, self-contained claims from a conversation segment.

WORTH — be selective; most segments yield FEW claims, and noise poisons memory
- Extract durable facts about the USER and THEIR world: identity, preferences, \
decisions, goals/intentions, projects, work, relationships, possessions, habits, \
and commitments.
- Do NOT transcribe external reference material the user is merely reading, \
researching, or being told about — how some other tool/library/product/feature \
works, documentation, search results, general knowledge. A whole conversation \
researching an external feature yields the user's DECISION or INTENT about it \
(e.g. "The user wants to build a goal feature in ntrp"), NOT a catalog of that \
feature's internals.
- Do NOT extract ephemeral operational chatter (tool status, acknowledgements like \
"ok"/"cool"/"let's try", run mechanics) or facts only true within this one session.
- Do NOT turn one task/debugging segment into durable memory: a SPECIFIC experiment- \
run config, an individual PR/commit/issue number, a transient build/test result, a \
one-off step the user took — these are work-in-progress, not durable knowledge. Keep \
the DURABLE residue (a decision made, an outcome reached, a stable preference or a \
fact about the user/their projects), drop the run-by-run mechanics. (e.g. keep "The \
user is researching memory-unit choices for ntrp"; drop "run stage3_x_800 used 800 \
controls".)
- When in doubt, DROP. A near-empty extract is the CORRECT result for a segment that \
taught the system nothing durable about the user.

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
- The subject is the ONE real-world referent the claim is ABOUT. \
canonical_subject is its stable, fully-resolved name — the string you'd use to \
look this entity up every time, regardless of how this turn referred to it. \
Normalize it so the SAME referent always gets the SAME string.
- A claim that CHARACTERIZES another person/entity is about THAT person, even if \
it also mentions the user. Use their proper name when known; if they are \
identified only by relationship, use a stable relational identifier as the name \
(e.g. "the user's wife", "the user's manager"). That other person IS the subject \
— do NOT fold such a claim onto "the user" just because the user is mentioned.
- "I"/"me"/"my"/"the user" referring to the assistant's principal resolves to \
that person's canonical name when scope makes it known; otherwise "the user".
- Two surface forms denoting the same referent in this segment MUST get the same \
canonical_subject.
- NEVER emit a bare pronoun or deictic alone as canonical_subject ("he", "she", \
"it", "they" are forbidden). A relational identifier anchored to a known party \
("the user's wife") IS allowed when the person has no proper name in the turn.
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
