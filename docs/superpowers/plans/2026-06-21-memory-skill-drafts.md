# Memory Skill Drafts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an Eve-style markdown skill bridge above memory without making memory itself a skill store.

**Architecture:** SQLite records remain canonical. Skills remain filesystem packages loaded by the existing `SkillRegistry`. Memory export generates read-only skill draft artifacts under `context/skill-drafts/`; promotion to a real skill still goes through existing approved `create_skill`.

**Tech Stack:** Python 3.13, `ArtifactMemoryStore`, existing skill registry/service, pytest.

---

## Guardrails

- Do not auto-create real skills from memory.
- Do not write to `agent/skills`, `.skills`, or `~/.ntrp/skills`.
- Do not add a new skill runtime, Eve runtime, sandbox, policy engine, or canonical memory kind.
- Keep generated draft pages read-only artifacts.
- Keep edits away from unrelated dirty files in `apps/server/ntrp/agent/`, `apps/server/ntrp/core/`, and `apps/server/tests/test_agent_lib.py`.

## Task 1: Generated Skill Draft Artifacts

**Files:**
- Modify: `apps/server/ntrp/memory/artifacts.py`
- Modify: `apps/server/tests/test_memory_artifacts.py`
- Modify: `docs/api-reference/memory.mdx`

- [ ] **Step 1: Write failing tests**

Add a memory artifact test with one directive and one fact/source. Expected behavior:

```python
draft_index = artifacts.read_artifact("context/skill-drafts/index.md")
draft = artifacts.read_artifact("context/skill-drafts/<expected-slug>.md")
assert draft.kind == "topic"
assert draft.record_count == 1
assert draft.source == "deterministic"
assert "not an installed skill" in draft.content
assert "create_skill" in draft.content
assert "Use when" in draft.content
assert "The user has a plain fact" not in draft_index.content
```

Also assert the draft pages are browseable via `list_artifacts(q="create_skill")`.

- [ ] **Step 2: Implement deterministic export**

In `ArtifactMemoryStore.export_from_records()`:

- Call `_write_skill_drafts(directives)` after `_write_context_docs()`.
- Generate `context/skill-drafts/index.md` on every export.
- Generate at most 25 draft pages from directive records only.
- Draft pages must state they are generated review surfaces, not installed skills.
- Draft pages should include:
  - source directive snippet
  - suggested skill name
  - suggested description
  - draft body seed
  - promotion instructions: review/rewrite, then use `create_skill`
- Use `_write()` and existing sanitizers.
- Set `meta.source="deterministic"` on draft pages.
- Avoid exposing raw record ids in page body.

- [ ] **Step 3: Update docs**

Update `docs/api-reference/memory.mdx` artifact section:

- Mention `context/skill-drafts/`.
- State drafts are generated from directives and are not installed skills.
- Promotion remains approval-gated through `create_skill`.

- [ ] **Step 4: Verify and commit**

Run from `apps/server`:

```bash
uv run pytest -q -p no:cacheprovider tests/test_memory_artifacts.py
```

Commit only touched files:

```bash
git add apps/server/ntrp/memory/artifacts.py apps/server/tests/test_memory_artifacts.py docs/api-reference/memory.mdx
git commit -m "Add memory skill draft artifacts"
```

## Task 2: Operator Skill Inventory Parity

**Files:**
- Modify: `apps/server/ntrp/operator/runner.py`
- Add or modify: `apps/server/tests/test_operator_runner.py`

- [ ] **Step 1: Write failing test**

Add a test that monkeypatches `create_agent` and calls `_prepare()` or `run_agent()` with a tiny `SkillRegistry` containing one skill. Assert the system prompt contains `<available_skills>` and the skill name/description.

- [ ] **Step 2: Implement parity**

In `apps/server/ntrp/operator/runner.py`:

```python
skills_context = deps.skill_registry.to_prompt_xml() if deps.skill_registry else None
system_prompt = build_system_prompt(
    ...,
    skills_context=skills_context,
)
```

Do not edit `core/prompts.py`.

- [ ] **Step 3: Verify and commit**

Run from `apps/server`:

```bash
uv run pytest -q -p no:cacheprovider tests/test_operator_runner.py tests/test_skills.py
```

Commit only touched files:

```bash
git add apps/server/ntrp/operator/runner.py apps/server/tests/test_operator_runner.py
git commit -m "Expose skills to operator runs"
```

## Final Verification

Run from `apps/server`:

```bash
uv run pytest -q -p no:cacheprovider tests/test_memory_artifacts.py tests/test_memory_router.py tests/test_memory_filesystem_tools.py tests/test_skills.py tests/test_operator_runner.py
```

Run from repo root:

```bash
git diff --check HEAD
git status --short
```
