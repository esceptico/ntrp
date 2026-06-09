"""Page-synthesis rubric for the lens OVERLAY.

A lens page is the editable human surface: the LLM re-renders the lens's member
records into a clean markdown directory. The model SELECTS and RE-WORDS for
reading; it never invents a fact not in the member list. Synthesis is pure
rendering — membership is decided elsewhere (LensStore's banded judge).

Adapted from the deleted claim-pipeline `prompts_project.py`: the `{{n}}`
anchor/citation scheme is dropped (it existed only for write-back diffing, which
we are not restoring), so the model emits plain readable markdown.
"""

PAGE_SYNTH_SYSTEM = """\
You render one "lens" — a named, criterion-defined view over a personal memory —
into a compact markdown DIRECTORY. The user wants a usable, readable page, not one
big note. You are given the lens name, its membership criterion, a target detail
level, and a list of member RECORDS (atomic statements).

Write a proper markdown document:
- If the records describe distinct entities (people, projects, things), make ONE
  `## {entity}` section each and write a tight profile from its records: short
  bullets for what is known, timeline/status when present, uncertainty when the
  records are weak. Do not write an essay.
- If the records are just a flat set of attributes about one thing, or no entities
  can be named, use a clean bulleted list instead of sections.
- Optionally open with ONE short orienting sentence (no heading). Do NOT restate or
  echo the lens criterion anywhere in the page.
- Merge near-duplicates; note contradictions inline.
- Render ONLY the records given. Never add a fact that is not in the list.
- Do not write a "members" count.

Detail levels:
- gist: a single short synthesized paragraph — no sections.
- structured: the full structured document above (the default).
- dossier: the structured document PLUS a final "## Details" section that lists
  each member record verbatim as a bullet.

Reason only over the content shown. Output the full markdown page as one string.
"""
