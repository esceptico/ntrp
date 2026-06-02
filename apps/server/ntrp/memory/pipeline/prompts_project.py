"""Page-synthesis rubric + structured-output schema (LENS_CONTRACTS §4.3).

The lens page is the editable human surface (Fork A / Karpathy-wiki style): the
LLM re-renders the lens's active members into prose. The model SELECTS and
RE-WORDS for reading; it never invents a claim and never adds a fact not in the
list. The page is synthesized from CLAIMS ONLY — never from another page (the
recursion guard, §4.3).

Anchoring is NOT the model's job (lessons.md: "don't require the model to
reproduce opaque ids"). Each member claim is shown with a short numbered tag
`{{n}}`; the model cites the claim it renders by that tag, e.g. `- runs 5k {{0}}`.
The projector then DETERMINISTICALLY rewrites each `{{n}}` into the stable
`<!--claim:ID-->` anchor post-synthesis (project.py). The model never sees, nor
echoes, the opaque claim id — so faithful synthesis can no longer "drop anchors"
and fall back to a raw list. A genuinely failed synthesis (blank output, or prose
that cites no claim at all) still degrades to a raw anchored list in the
projector (§9.5), never to a blank or hallucinated page.

Membership is decided elsewhere (LensMembership, the sole decision channel,
§0/§3.1). Synthesis is pure rendering: it makes NO keep/drop call.
"""

from pydantic import BaseModel, Field

PAGE_SYNTH_SYSTEM = """\
You render one "lens" — a named, criterion-defined view over a personal knowledge
base — into a compact markdown DIRECTORY. The user wants a usable list, not one big
note. You are given the lens name, its membership criterion, a target detail level,
and a NUMBERED list of member claims, each tagged {{0}}, {{1}}, {{2}}, ….

Write a proper markdown document organized as list/profile rows:
- Identify the distinct records represented in the member claims and make ONE
  `## {record}` section per record when the claims support record-level profiles.
- Under each `## {record}`, write a tight profile from the supporting claims: short
  bullets for what is known, timeline/status when present, and uncertainty when the
  claims are weak. Do not write an essay.
- If the claims are truly just a flat set of attributes about one record, or the
  records cannot be named from the claims, use a clean bulleted list instead of
  sections.
- Optionally open with ONE short orienting sentence (no heading). Do NOT restate or
  echo the lens criterion anywhere in the page.
- Merge near-duplicates, note contradictions inline.
- Render ONLY the claims given. Never add a fact that is not in the list.
- Cite the source claim wherever you use it by appending its index tag inline, e.g.
  "Runs 5k every morning {{0}}." or "- Lives in Lisbon {{3}}". A merged statement cites
  every index it covers, e.g. "Runs daily {{0}} {{3}}." EVERY index you were given MUST
  appear at least once somewhere on the page. Cite ONLY with this {{n}} tag — never
  invent other bracketed numbers.
- Do not echo the criterion text as a fact. Do not write a "members" count.

Detail levels:
- gist: a single short synthesized paragraph — no sections, no index tags.
- structured: the full structured document above (the default).
- dossier: the structured document PLUS a final "## Evidence" section listing each
  claim with its index tag.

Reason only over the content shown. Output the full markdown page as one string.
"""


class PageSynthesis(BaseModel):
    markdown: str = Field(description="the full markdown page, claims cited by {{n}} index")


PROFILE_SYNTH_SYSTEM = """\
You render ONE subject's profile inside a grouped lens view — a compact, readable
note about that subject. You are given the subject name, the lens criterion, a
detail level, and a NUMBERED list of the claims about THIS subject, each tagged
{{0}}, {{1}}, ….

Write a tight, well-formed profile:
- Lead with a 1–3 sentence synthesis of who/what this subject is and how they relate
  to the user, drawn only from the claims.
- If the lens criterion includes a "## Profile shape" with fields, capture those
  fields (as a short labelled bullet each). Otherwise a few grouped bullets for
  specifics. Merge near-duplicates and note contradictions inline.
- Render ONLY the claims given. Never add a fact not in the list.
- Cite each claim inline by its index tag where you use it. A merged statement cites
  every index it covers. EVERY index given MUST appear at least once. Cite ONLY with
  this {{n}} tag — never invent other bracketed numbers.
- Do NOT write a "## <subject>" heading — the caller adds it. Do not echo the
  criterion as a fact. Do not write a count.

Reason only over the content shown. Output the markdown profile as one string.
"""
