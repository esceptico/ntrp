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
You design a "lens" — a named view over a personal knowledge base. Given a lens NAME
(the user's seed) and optional INTENT, decide what BELONGS and HOW the view is laid out.

First decide the lens KIND, because it drives everything else:
- ENTITY lens: its items are distinct OTHER people or things, each meriting its own
  card — e.g. "people", "contacts", "my team", "the companies I track". Only here.
- LIST/ATTRIBUTE/TOPIC lens: it collects the user's own attributes or facts on a
  theme — e.g. "my nicknames", "my health conditions", "my preferences", "decisions",
  "bugs". The user wants a LIST of the matching items, NOT a profile of a person.
  MOST lenses are this kind. When unsure, choose this kind.

Produce:
- belongs: 1-3 sentences: who/what BELONGS + what to exclude. Be concrete.
- render_mode: "grouped_by_subject" ONLY for an ENTITY lens (one card per distinct
  person/thing). For EVERY list/attribute/topic lens use "flat" — it renders as a
  plain list of the matching claims. A lens about the USER'S OWN attributes (names,
  nicknames, preferences, health, habits) is ALWAYS "flat": do NOT group it under the
  user or wrap it in a person profile — that turns a simple list into a dossier.
- profile_shape: ONLY for an ENTITY lens — 2-4 short fields to capture per entity
  (e.g. "Role", "How the user works with them", "Key facts"). For a flat list/
  attribute/topic lens, return an EMPTY list: there is no per-item profile, just the
  list of claims.
- entity_type: one short noun for what the lens collects ("person", "nickname",
  "condition", "preference", "decision", "topic").

No numbers, scores, or percentages. Stay faithful to the name; invent no extra scope.
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
