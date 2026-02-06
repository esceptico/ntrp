SUMMARIZE_PROMPT_TEMPLATE = """You are continuing an active personal assistant session.
Create a state handoff for seamless continuation. Target length: ~{budget} words.

## Required Sections:

### Active Objective
What is the user trying to accomplish RIGHT NOW?

### Open Loops
- Pending follow-ups with who/what/when
- Unanswered questions
- Promised actions
Format: "- [item] (source: note:path, email:id, raw_item:id, or unverified)"

### Next Actions
Ordered checklist of what should happen next (3-8 items)

### Key Facts
ONLY facts that affect next actions. For each fact:
- Include source pointer if available: (source: note:path, email:id, raw_item:id)
- If no source, mark as: (unverified)

### Pointers
List of identifiers that may need retrieval:
- note paths referenced
- raw_item IDs for full content
- email IDs

## Rules:
- If a fact cannot be traced to a source, mark (unverified)
- Do NOT restate general preferences unless relevant to current objective
- Focus on CONTINUING work, not documenting history
- Be terse. State, not story."""
