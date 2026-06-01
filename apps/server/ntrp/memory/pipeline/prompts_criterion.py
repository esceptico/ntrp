"""Criterion-synthesis rubric + structured-output schema (LLooM seed→criterion).

A lens's criterion is a one-sentence, user-editable inclusion prompt (spec §2/§3).
This module authors that text from a lens NAME (LLooM's seed), so the user only has
to name a view; the system drafts the criterion they then edit.

This authors TEXT only. It makes NO membership decision — every keep/drop call still
goes through LensMembership (the sole decision channel, §0). Nothing here is a
keyword/regex/threshold gate.
"""

from pydantic import BaseModel, Field

CRITERION_SYNTH_SYSTEM = """\
You author the inclusion criterion for a "lens" — a named, criterion-defined view
over a personal knowledge base — and decide how the view is laid out. You are given
a lens NAME (the user's seed) and an optional INTENT.

Produce two things:
1) criterion — ONE natural-language sentence an LLM judge applies to a single memory
   claim to decide membership. It must be a PRECISE, complete definition of what
   belongs, not a vague restatement of the name.
2) render_mode — "grouped_by_subject" when the lens is about PEOPLE or other distinct
   ENTITIES (so the view shows one profile card per individual); otherwise "flat".

Rules for the criterion:
- Exactly ONE sentence. No examples, lists, numbers, scores, or percentages.
- If the lens is about PEOPLE / individuals / relationships, scope it to claims that
  are about a SPECIFIC individual (a named contact, colleague, family member) or a
  relationship between people — and EXCLUDE the user's own generic preferences,
  habits, settings, health, or work style. A claim merely mentioning the user is NOT
  "about a person".
- If the lens is a TOPIC (bugs, preferences, health, decisions…), define that topic
  precisely.
- Stay faithful to the name; do not invent unrelated scope.

Rules for render_mode:
- "grouped_by_subject" ONLY for people/entity lenses where one card per subject makes
  sense ("people", "contacts", "team", a family). Every topic lens is "flat".
"""


class SynthesizedCriterion(BaseModel):
    criterion: str = Field(description="one-sentence natural-language inclusion criterion")
    render_mode: str = Field(
        default="flat",
        description='"grouped_by_subject" for people/entity lenses (one card per individual), else "flat"',
    )
