"""Page-synthesis rubric + structured-output schema (LENS_CONTRACTS §4.3).

The lens page is the editable human surface (Fork A / Karpathy-wiki style): the
LLM re-renders the lens's active members into prose. The model SELECTS and
RE-WORDS for reading; it never invents a claim and never adds a fact not in the
list. The page is synthesized from CLAIMS ONLY — never from another page (the
recursion guard, §4.3).

Anchoring is NOT the model's job (lessons.md: "don't require the model to
reproduce opaque ids"). Each member claim is shown with a short numbered tag
`[n]`; the model cites the claim it renders by that tag, e.g. `- runs 5k [0]`.
The projector then DETERMINISTICALLY rewrites each `[n]` into the stable
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
base — into a single readable markdown page. You are given the lens name, its
membership criterion, a target detail level, and a NUMBERED list of member claims.
Each claim is tagged with a short index like [0], [1], [2].

Write the page as markdown. Group and order the claims so they read well; reword
for flow and merge near-duplicates into one line; note contradictions inline. But:

- Render ONLY the claims given. Never add a fact that is not in the list.
- Every claim you render MUST cite its index tag at the END of its line, e.g.
  `- Runs 5k every morning. [0]`. One claim per bullet line under the body
  sections. Cite the index verbatim — copy the bracketed number you were given.
- If two claims say the same thing, render one bullet and cite BOTH indexes on
  that line, e.g. `- Runs daily. [0] [3]`. Every index you were given must appear
  on exactly one rendered line.
- Do not echo the criterion text as a fact. Do not write a "members" count.
- detail=gist: a single short synthesized paragraph, no bullets, no index tags.
- detail=structured: a "## Profile" section of cited bullet lines (the default).
- detail=dossier: the structured bullets PLUS a "## Evidence" section; keep the
  index tags on the profile bullets.

Reason only over the content shown. Output the full markdown page as a single
string field.
"""


class PageSynthesis(BaseModel):
    markdown: str = Field(description="the full markdown page, claims cited by [n] index")


PROFILE_SYNTH_SYSTEM = """\
You render ONE subject's profile inside a grouped lens view. You are given the
subject name, the lens criterion, a detail level, and a NUMBERED list of the
claims about THIS subject. Each claim is tagged with a short index like [0], [1].

Write a compact profile (a few sentences or a short bullet list) about this one
subject. Same contract as page synthesis:

- Render ONLY the claims given. Never add a fact not in the list.
- Every claim you render MUST cite its index tag at the END of its line, e.g.
  `- CEO of ThirdLayer. [0]`. One claim per bullet line.
- If two claims say the same thing, render one bullet and cite BOTH indexes.
- Do NOT write a "## <subject>" heading — the caller adds it. Do not echo the
  criterion as a fact. Do not write a count.

Reason only over the content shown. Output the markdown profile as one string.
"""
