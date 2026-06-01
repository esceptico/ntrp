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
over a personal knowledge base. You are given a lens NAME (the user's seed) and an
optional INTENT. Write ONE natural-language sentence that tests whether a memory
item belongs in this lens, phrased as "this item is about / describes / records …".

Rules:
- Output exactly ONE sentence. No examples, no bullet lists, no numbered points.
- No numeric thresholds, no scores, no percentages — it is a natural-language test,
  not a rule.
- Resolve the obvious reading of the name: a person's name → "this item is about
  <that person>"; a topic → "this item describes <that topic>". Stay faithful to
  the name; do not invent unrelated scope.
- Keep it tight and self-contained so an LLM judge can apply it to one claim.

Output the single criterion sentence in the one field.
"""


class SynthesizedCriterion(BaseModel):
    criterion: str = Field(description="one-sentence natural-language inclusion criterion")
