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
You author a "lens" — a named, criterion-defined view over a personal knowledge base
(Lens spec §0-§2). A lens selects a slice of claims by a natural-language criterion
and renders as a synthesized markdown page that is a STRUCTURED LIST of the matching
claims (deduped, cross-referenced). Topics ("bugs"), the user's own categories ("my
nicknames", "my health conditions", "personal traits"), and people are all lenses.

Given a lens NAME (the seed) and optional INTENT, produce:
- belongs: 1-3 sentences — the inclusion test: who/what BELONGS + what to exclude.
  Be concrete. Define the slice; the page will list the claims that match it.
- profile_shape: OPTIONAL 2-4 short facets worth capturing per matching item, used
  only to organize the list (e.g. for a contact: "Role", "How the user works with
  them"). Leave EMPTY for a plain list lens (e.g. "my nicknames" → just the list of
  names). Never use it to wrap the user's own attributes into a single person profile.
- entity_type: one short noun for what the lens collects ("person", "nickname",
  "condition", "preference", "decision", "topic").

No numbers, scores, or percentages. Stay faithful to the name; invent no extra scope.
"""


class SynthesizedCriterion(BaseModel):
    belongs: str = Field(description="1-3 sentences: who/what belongs + what to exclude")
    profile_shape: list[str] = Field(
        default_factory=list, description="2-4 short fields each member's profile captures"
    )
    entity_type: str = Field(
        default="thing",
        description='the kind of thing grouped, e.g. "person", "project", "topic"',
    )
