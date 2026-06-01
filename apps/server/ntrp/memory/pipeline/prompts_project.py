"""Page-synthesis rubric + structured-output schema (LENS_CONTRACTS §4.3).

The lens page is the editable human surface (Fork A / Karpathy-wiki style): the
LLM re-renders the lens's active members into prose, but every claim_id anchor it
is given MUST be echoed back verbatim. The model SELECTS and RE-WORDS for reading;
it never invents an anchor and never fabricates a claim. The page is synthesized
from CLAIMS ONLY — never from another page (the recursion guard, §4.3).

Membership is decided elsewhere (LensMembership, the sole decision channel,
§0/§3.1). Synthesis is pure rendering: it makes NO keep/drop call, so nothing here
gates membership. A failed/empty synthesis degrades to a raw anchored list in the
projector (§9.5), never to a blank or hallucinated page.
"""

from pydantic import BaseModel, Field

PAGE_SYNTH_SYSTEM = """\
You render one "lens" — a named, criterion-defined view over a personal knowledge
base — into a single readable markdown page. You are given the lens name, its
membership criterion, a target detail level, and a NUMBERED list of member claims.
Each claim carries a stable anchor id.

Write the page as markdown. Group and order the claims so they read well; reword
for flow and merge near-duplicates into one line; note contradictions inline. But:

- Render ONLY the claims given. Never add a fact that is not in the list. Never
  invent or drop an anchor.
- Every claim you render MUST end its line with its anchor, copied verbatim, as an
  HTML comment: `- <your wording> <!--claim:THE_ID-->`. One claim per bullet line
  under the body sections.
- If two claims say the same thing, render one bullet and append BOTH anchors to
  that line. Every input anchor must appear on exactly one rendered line.
- Do not echo the criterion text as a fact. Do not write a "members" count.
- detail=gist: a single short synthesized paragraph, no bullets, no anchors.
- detail=structured: a "## Profile" section of anchored bullet lines (the default).
- detail=dossier: the structured bullets PLUS a "## Evidence" section; keep anchors
  on the profile bullets.

Reason only over the content shown. Output the full markdown page as a single
string field.
"""


class PageSynthesis(BaseModel):
    markdown: str = Field(description="the full markdown page, anchors echoed verbatim")


PROFILE_SYNTH_SYSTEM = """\
You render ONE subject's profile inside a grouped lens view. You are given the
subject name, the lens criterion, a detail level, and a NUMBERED list of the
claims about THIS subject. Each claim carries a stable anchor id.

Write a compact profile (a few sentences or a short bullet list) about this one
subject. Same contract as page synthesis:

- Render ONLY the claims given. Never add a fact not in the list. Never invent or
  drop an anchor.
- Every claim you render MUST end its line with its anchor, copied verbatim, as an
  HTML comment: `- <your wording> <!--claim:THE_ID-->`. One claim per bullet line.
- If two claims say the same thing, render one bullet and append BOTH anchors.
- Do NOT write a "## <subject>" heading — the caller adds it. Do not echo the
  criterion as a fact. Do not write a count.

Reason only over the content shown. Output the markdown profile as one string.
"""
