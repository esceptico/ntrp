---
name: propose-skill
description: Use this skill when the user wants to capture the current conversation as a reusable skill. Analyzes the session and emits a structured skill proposal the UI can render as a card.
---

# Propose Skill

The user wants to capture the work in this conversation as a reusable skill — a procedure the agent can re-run on demand via `/<skill-name>`. Your job: produce ONE proposal as a fenced JSON block the UI will render as an interactive card.

## When a skill (vs. an automation)

- **Skill**: a *procedure* the user invokes by name. No schedule. Captures know-how (steps, gotchas, references).
- **Automation**: a scheduled run with a fixed prompt. If the work has a clear cadence, propose an automation instead — use `/propose-automation`.

## What to look at

- The actual steps you took in this session (tool calls, files touched, decisions made)
- What was tricky or non-obvious — the value of a skill is in the gotchas
- Whether the work has a clear sequence of steps worth codifying
- A skill name that's lowercase, hyphenated, and reads like an imperative (`refactor-component`, `audit-secrets`)

## Output format

Respond with a **short** preamble (1-2 sentences max) then a single fenced code block tagged `ntrp-proposal` containing ONLY valid JSON with these fields:

````
```ntrp-proposal
{
  "kind": "skill",
  "name": "<lowercase-hyphenated-name, max 48 chars>",
  "description": "<one-line description matching user intent — what to do AND when to use it>",
  "body": "<the full SKILL.md body, after the frontmatter. Step-by-step instructions. Use markdown. Escape newlines as \\n.>",
  "rationale": "<2-3 lines citing specific evidence from THIS session: which steps, what tools, why this is worth codifying.>"
}
```
````

## Rules

- **One proposal only.** Pick the highest-value one if there are multiple candidates.
- **Grounded.** `rationale` must reference what actually happened in this session — specific tools, files, decisions. No generic "users often want to…" boilerplate.
- **`body` is the SKILL.md body.** No frontmatter (the system adds that from `name` + `description`). Start with `# Title`. Include step-by-step instructions, gotchas, examples. Write it for the *next* agent invocation — that agent has no memory of this conversation.
- **No code outside the JSON block.** Escape newlines as `\n` inside JSON string values.

## If there's nothing reusable

If the conversation is a one-off Q&A or exploration with no procedure worth codifying, say so plainly in 1-2 sentences and skip the JSON block. Don't manufacture a proposal.
