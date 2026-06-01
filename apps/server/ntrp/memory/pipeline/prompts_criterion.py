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
You design a "lens" — a named directory over a personal knowledge base that groups
related memory claims and defines how each member's profile is shaped. You are given
a lens NAME (the user's seed) and an optional INTENT. Produce:

- belongs: 1-3 sentences defining who/what BELONGS in this lens AND what to exclude.
  Be concrete. For a PEOPLE lens, scope to specific individuals or relationships and
  EXCLUDE the user's own generic preferences, habits, settings, health, or work
  style — a claim merely mentioning the user is not "about a person".
- profile_shape: 2-4 short fields each member's profile should capture. For a person
  lens e.g. "Role / what they own", "How the user works with them", "Key facts". For
  a topic lens, the facets worth tracking per item.
- render_mode: "grouped_by_subject" when the lens groups distinct PEOPLE or ENTITIES
  (so the view shows one profile per individual); otherwise "flat".
- entity_type: the kind of thing this lens groups, e.g. "person", "project",
  "library", "decision", "topic". One short noun.

No numbers, scores, or percentages anywhere. Stay faithful to the name; do not invent
unrelated scope.
"""


class SynthesizedCriterion(BaseModel):
    belongs: str = Field(description="1-3 sentences: who/what belongs + what to exclude")
    profile_shape: list[str] = Field(
        default_factory=list, description="2-4 short fields each member's profile captures"
    )
    render_mode: str = Field(
        default="flat",
        description='"grouped_by_subject" for people/entity lenses (one profile per individual), else "flat"',
    )
    entity_type: str = Field(
        default="thing",
        description='the kind of thing grouped, e.g. "person", "project", "topic"',
    )
