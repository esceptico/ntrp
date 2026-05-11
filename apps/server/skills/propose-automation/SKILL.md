---
name: propose-automation
description: Use this skill when the user wants to turn the current conversation into a scheduled automation. Analyzes the session and emits a structured automation proposal the UI can render as a card.
---

# Propose Automation

The user wants to capture the work in this conversation as a reusable scheduled automation. Your job: produce ONE proposal as a fenced JSON block the UI will render as an interactive card.

## What to look at

- The user's intent across the conversation (what were they trying to accomplish?)
- The actual tools you ran and what they returned
- Any recurring or time-based intent ("every morning", "weekly", "after deploys")
- The single most reusable shape of the task — not a literal replay

## Output format

Respond with a **short** preamble (1-2 sentences max) then a single fenced code block tagged `ntrp-proposal` containing ONLY valid JSON with these fields:

````
```ntrp-proposal
{
  "kind": "automation",
  "name": "<short imperative phrase, max 60 chars>",
  "prompt": "<the prompt the agent should run on each tick — full, self-contained, no references to 'this conversation'>",
  "schedule": "<one of: 'once' | 'every N minutes/hours/days' | 'every weekday HH:MM' | 'daily HH:MM' | 'weekly DAY HH:MM' — be specific>",
  "rationale": "<2-3 lines citing specific evidence from THIS session: which tools, what output, what pattern made you suggest this. Be concrete, not generic.>"
}
```
````

## Rules

- **One proposal only.** Pick the highest-value one if there are multiple candidates.
- **Grounded.** `rationale` must reference what actually happened in this session — specific tool calls, file paths, results. No generic "users often want to…" boilerplate.
- **Schedule must be specific.** If the user mentioned a time, use it. If they didn't but the task feels recurring, infer a sensible cadence. If it's clearly one-off, use `"once"`.
- **`prompt` is what runs without you.** It must stand alone. The future agent has no memory of this conversation. Be explicit about what to do, which sources to check, what to output.
- **No code outside the JSON block.** No markdown formatting inside JSON values. Escape newlines as `\n`.

## If there's nothing reusable

If the conversation isn't a good automation candidate (one-off Q&A, exploratory chat with no shape), say so plainly in 1-2 sentences and skip the JSON block. Don't manufacture a proposal.
