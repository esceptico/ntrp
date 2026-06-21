# Memory Skill Candidates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an Eve-style markdown skill bridge above memory without making memory itself a skill store.

**Architecture:** SQLite records remain canonical. Skills remain filesystem packages loaded by the existing `SkillRegistry`. Memory export generates read-only skill candidate artifacts under `context/skill-candidates/`; promotion to a real skill still goes through existing approved `create_skill`.

**Tech Stack:** Python 3.13, `ArtifactMemoryStore`, existing skill registry/service, pytest.

---

## Guardrails

- Do not auto-create real skills from memory.
- Do not write to `agent/skills`, `.skills`, or `~/.ntrp/skills`.
- Do not add a new skill runtime, Eve runtime, sandbox, policy engine, or canonical memory kind.
- Keep generated candidate pages read-only artifacts.
- Keep edits away from unrelated dirty files in `apps/server/ntrp/agent/`, `apps/server/ntrp/core/`, and `apps/server/tests/test_agent_lib.py`.

## Task 1: Generated Skill Candidate Artifacts

**Files:**
- Modify: `apps/server/ntrp/memory/artifacts.py`
- Modify: `apps/server/tests/test_memory_artifacts.py`
- Modify: `docs/api-reference/memory.mdx`

- [ ] **Step 1: Write failing tests**

Add a memory artifact test with one directive and one fact/source. Expected behavior:

```python
candidate_index = artifacts.read_artifact("context/skill-candidates/index.md")
candidate = artifacts.read_artifact("context/skill-candidates/<expected-slug>.md")
assert candidate.kind == "topic"
assert candidate.record_count == 1
assert candidate.source == "deterministic"
assert "not an installed skill" in candidate.content
assert "create_skill" in candidate.content
assert "Use when" in candidate.content
assert "The user has a plain fact" not in candidate_index.content
```

Also assert the candidate pages are browseable via `list_artifacts(q="create_skill")`.

- [ ] **Step 2: Implement deterministic export**

In `ArtifactMemoryStore.export_from_records()`:

- Call `_write_skill_candidate_context(directives, labels_by_id)` after `_write_context_docs()`.
- Generate `context/skill-candidates/index.md` on every export.
- Generate at most 25 candidate pages from directive records only.
- Candidate pages must state they are generated review surfaces, not installed skills.
- Candidate pages should include:
  - source directive snippet
  - suggested skill name
  - suggested description
  - draft body seed
  - promotion instructions: review/rewrite, then use `create_skill`
- Use `_write()` and existing sanitizers.
- Set `meta.source="deterministic"` on candidate pages.
- Avoid exposing raw record ids in page body.

- [ ] **Step 3: Update docs**

Update `docs/api-reference/memory.mdx` artifact section:

- Mention `context/skill-candidates/`.
- State candidates are generated from directives and are not installed skills.
- Promotion remains approval-gated through `create_skill`.

- [ ] **Step 4: Verify and commit**

Run from `apps/server`:

```bash
uv run pytest -q -p no:cacheprovider tests/test_memory_artifacts.py
```

Commit only touched files:

```bash
git add apps/server/ntrp/memory/artifacts.py apps/server/tests/test_memory_artifacts.py docs/api-reference/memory.mdx
git commit -m "Add memory skill candidate artifacts"
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
