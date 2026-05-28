# Slice 7 — Skill inducer + `is_toolable` gate + `proposal` flow

**Status:** Draft for PM A/B gate, then codex fire. **PRE-REQUISITES: slices 5 + 6 must land first.** Brief is speculative; revise post-slice-6 if claim/contradiction shape diverges.
**Prereqs:** slice 6 shipped. Claim layer producing `kind=claim` rows with `is_toolable` field on metadata (added in this slice). Contradiction watcher resolving conflicts. Test baseline ≥ 856 passed.
**Backlog absorbed from `slice-07-backlog.md`:** §2B (`test_knowledge_write_gate.py` — 30 tests, 29 dead; reborn as proposal-gate tests against the new `kind=proposal` flow).
**Out of scope:** UI for skill proposals (post-slice-7, separate UX slice), entity-resolution-driven skill grouping (slice 8+), skill-execution runtime changes (skills already execute via existing `~/.ntrp/skills/<name>/SKILL.md` loading).

---

## 0. TL;DR

Add the `SkillInducer` that scans `kind=claim` rows for patterns matching the `is_toolable` gate (repetition + determinism + trigger + success-signal per spec §3.5). Gate-passing patterns produce `kind=proposal` rows with a draft SKILL.md body in `/tmp/ntrp/proposed-skills/`. User approval (via `POST /admin/memory/proposals/{id}/approve`) flips the proposal to `kind=skill`, moves the file to `~/.ntrp/skills/<name>/SKILL.md`, and writes an evidence-edge back to the claim cluster that induced it. Rejection (`/admin/memory/proposals/{id}/reject`) deletes the draft file and marks the proposal `status='rejected'`. This is the CL payoff: future behavior changes via approved skills.

---

## 1. Goal — concrete

After slice 7 ships:

1. Pass 2 produces a `kind=claim` row (slice 5).
2. **NEW:** Each new claim is scanned via `IsToolableGate.evaluate(claim)` to set `metadata.is_toolable: bool` + `metadata.toolable_reason: str`.
3. **NEW:** `SkillInducer.run()` (daily scheduler + manual endpoint) finds clusters of `is_toolable=True` claims sharing trigger + workflow shape, drafts SKILL.md content via LLM, writes `kind=proposal` rows.
4. **NEW:** `GET /admin/memory/proposals` lists open proposals with diff vs existing skills.
5. **NEW:** `POST /admin/memory/proposals/{id}/approve` promotes proposal → skill: write `kind=skill` row, move SKILL.md from `/tmp/ntrp/proposed-skills/` to `~/.ntrp/skills/<name>/`, add `role='derives_from'` edges from skill to source claims, set proposal `status='approved'`.
6. **NEW:** `POST /admin/memory/proposals/{id}/reject` marks proposal `status='rejected'`, deletes draft file.
7. **NEW:** Retrieval surfaces `kind=skill` rows with `reason='skill_match'` when a user query semantically matches a skill's trigger.

**Verification:** seed DB with 4 claims describing a repeated workflow (e.g. "user triages PRs every morning", "user uses gh CLI for triage", "user files notes in Notion after triage", "user assigns reviewers based on file paths"). Run skill-inducer. Assert: 1 proposal row created with draft SKILL.md containing those steps. Approve it. Assert: skill row + file at `~/.ntrp/skills/<name>/SKILL.md` + edges back to the 4 claims.

---

## 2. Hard scope boundaries

### Files codex MAY touch

**Add:**
- `apps/server/ntrp/memory/skill_inducer.py` — `SkillInducer`, `IsToolableGate`, `ProposalDraft` dataclass, scoring helpers.
- `apps/server/ntrp/memory/prompts/is_toolable.txt` — LLM prompt for borderline toolability judgment.
- `apps/server/ntrp/memory/prompts/skill_draft.txt` — LLM prompt for SKILL.md body drafting.
- `apps/server/tests/memory/test_skill_inducer.py` — ≥ 15 tests (higher bar than slices 5/6 because backlog §2B contributes ~10 ported cases).
- `apps/server/tests/memory/test_proposal_flow.py` — ≥ 8 tests for approve/reject endpoints.

**Modify:**
- `apps/server/ntrp/memory/pattern_finder.py` — `_persist_claim` calls `IsToolableGate.evaluate_and_tag(claim_id)` after the contradiction watcher fires (so superseded claims don't get the toolable scan). One added line at end of method. No other changes.
- `apps/server/ntrp/memory/retrieval.py` — extend reason-label set with `'skill_match'`. One branch added.
- Slice-5/6 admin router — add 4 endpoints: `/admin/memory/skill-inducer/run`, `/admin/memory/proposals`, `/admin/memory/proposals/{id}/approve`, `/admin/memory/proposals/{id}/reject`.
- The slice-4/5 scheduler — add `skill-inducer-daily` registration (06:00 UTC, 1-hour after pass-2 scheduler).

### Files codex MUST NOT touch (frozen zones)

- `apps/server/ntrp/memory/connectors/*`, `buffers_store.py`, `episode_close.py`, `activation.py` — slices 2/3.
- `apps/server/ntrp/memory/pattern_finder.py` body — EXCEPT the one-line `IsToolableGate.evaluate_and_tag` call. Do NOT refactor pass-1/pass-2 or the slice-6 contradiction hook.
- `apps/server/ntrp/memory/contradictions.py` — slice 6 module, frozen.
- `apps/server/ntrp/knowledge/skill_promotions.py`, `write_gate.py`, `fact_consolidation.py`, `contradictions.py` — old knowledge layer. Deprecation comments only. They remain referenced by knowledge routes / desktop UI; removal is post-slice-7 cleanup.
- `~/.ntrp/skills/*/SKILL.md` files — existing skills are untouched. New skills land in their own directories.

### Files codex MUST NOT delete

No deletions. The old knowledge layer stays in place until a follow-up cleanup slice.

---

## 3. The `is_toolable` gate

Per spec §3.5, four criteria. Each is a method on `IsToolableGate`:

### 3.1 Repetition

```python
async def _check_repetition(self, claim: MemoryItem) -> tuple[bool, str]:
    evidence_count = await self.repo.count_parents(item_id=claim.id, role="evidence")
    if evidence_count < self.min_episodes:  # default 3
        return False, f"only {evidence_count} supporting episodes (need ≥ 3)"
    return True, f"{evidence_count} supporting episodes"
```

### 3.2 Determinism

```python
async def _check_determinism(self, claim: MemoryItem) -> tuple[bool, str]:
    # Pull supporting episodes via evidence edges
    episodes = await self.repo.get_evidence_chain(claim.id, max_depth=2, kind="episode")
    if len(episodes) < 2:
        return False, "no episode chain to evaluate variance"
    # Jaccard over each episode's tool-call sequence
    sequences = [tuple(ep.metadata.get("tool_sequence", [])) for ep in episodes]
    if not all(sequences):
        return False, "episodes lack tool_sequence metadata"
    avg_jaccard = _mean_pairwise_jaccard(sequences)
    if avg_jaccard < 0.7:
        return False, f"tool-sequence Jaccard {avg_jaccard:.2f} < 0.7"
    return True, f"deterministic (Jaccard {avg_jaccard:.2f})"
```

`tool_sequence` is added to episode metadata in this slice (the connector already records tool calls — we add a `tool_sequence` projection at episode-close time). **EXCEPTION to the frozen zone**: codex MAY add one field to the episode-close metadata payload. Document in §10.

### 3.3 Trigger identification

```python
async def _check_trigger(self, claim: MemoryItem) -> tuple[bool, str]:
    # Use LLM judge to extract a trigger phrase from the claim + episodes
    trigger = await self._extract_trigger_with_llm(claim)
    if trigger is None or trigger == "unclear":
        return False, "no identifiable trigger"
    # Store on metadata for skill-draft step
    await self.repo.update_metadata_key(claim.id, "induced_trigger", trigger)
    return True, f"trigger: '{trigger}'"
```

LLM prompt:
```
Given this claim and supporting episodes, identify the precondition or trigger that starts the workflow.

Claim: {claim_content}
Episodes:
{episode_bullets}

Answer with ONE short phrase (≤ 10 words) describing when this workflow begins, or the word "unclear" if no consistent trigger exists.
```

### 3.4 Success signal

```python
async def _check_success_signal(self, claim: MemoryItem) -> tuple[bool, str]:
    episodes = await self.repo.get_evidence_chain(claim.id, max_depth=2, kind="episode")
    # Two ways to count "success":
    #   (a) explicit positive feedback metadata (already tracked per ntrp directives)
    #   (b) absence of correction within 24h of episode close
    success_count = sum(1 for ep in episodes if self._episode_succeeded(ep))
    success_rate = success_count / max(len(episodes), 1)
    if success_rate < 0.6:
        return False, f"success rate {success_rate:.0%} < 60%"
    return True, f"{success_count}/{len(episodes)} episodes succeeded"
```

`self._episode_succeeded(ep)` checks `ep.metadata.get("feedback_score", 0) > 0` OR (`ep.closed_at` exists AND no episode within 24h tagged as `"correction_of": ep.id`).

### 3.5 Aggregate

```python
async def evaluate(self, claim: MemoryItem) -> tuple[bool, str]:
    checks = [
        await self._check_repetition(claim),
        await self._check_determinism(claim),
        await self._check_trigger(claim),
        await self._check_success_signal(claim),
    ]
    passed = all(ok for ok, _ in checks)
    reason = "; ".join(msg for _, msg in checks)
    return passed, reason

async def evaluate_and_tag(self, claim_id: str) -> None:
    claim = await self.repo.get_item(claim_id)
    is_toolable, reason = await self.evaluate(claim)
    metadata = dict(claim.metadata)
    metadata["is_toolable"] = is_toolable
    metadata["toolable_reason"] = reason
    metadata["toolable_evaluated_at"] = now_iso()
    await self.repo.update_metadata(item_id=claim_id, metadata=metadata)
```

---

## 4. Skill inducer — clustering toolable claims

`SkillInducer.run(window_days=30, scope='user')`:

1. Fetch all `kind=claim` rows where `metadata.is_toolable=True` AND no existing `kind=proposal` derives from this claim (via reverse edge lookup).
2. Cluster by `induced_trigger` similarity (string Jaccard on trigger phrases) + entity overlap. Min cluster size: 1 (a single toolable claim can become a skill).
3. For each cluster, draft SKILL.md body via LLM (prompt §5).
4. Write `kind=proposal` row + `/tmp/ntrp/proposed-skills/<slug>/SKILL.md` file + `role='derives_from'` edges to source claims.

`PatternFinderProposalRunResult` dataclass mirrors the slice-4/5 result shape (`claims_considered`, `proposals_written`, `elapsed_ms`).

---

## 5. SKILL.md drafting

`apps/server/ntrp/memory/prompts/skill_draft.txt`:

```
You are drafting a reusable skill in Markdown.

The skill formalizes this recurring workflow:

Trigger: {trigger}
Claim(s):
{claim_bullets}

Supporting episodes (concrete examples):
{episode_bullets}

Write a SKILL.md body with this exact structure:

# <Skill name in Title Case>

## When to use
<1-2 sentences describing the trigger condition>

## Steps
1. <step>
2. <step>
...

## Inputs
- <named input, if any>

## Outputs
- <named output, if any>

## Notes
<any caveats, edge cases, or invariants from the evidence>

Keep it concrete. Use the user's actual vocabulary from the claims/episodes. Do NOT invent steps that weren't supported by the evidence.
```

Skill slug derived from the title: lowercase, hyphenated, ASCII-only.

---

## 6. Proposal lifecycle

### 6.1 Storage

`kind=proposal` row:
```python
MemoryItem(
    kind="proposal",
    scope=scope,
    content=draft_skill_md,         # full SKILL.md body in content
    tags=["proposal", "skill-draft"] + topic_tags,
    metadata={
        "proposal_type": "skill",
        "skill_slug": slug,
        "draft_path": "/tmp/ntrp/proposed-skills/<slug>/SKILL.md",
        "induced_trigger": trigger,
        "source_claim_ids": [...],
        "status": "open",  # open | approved | rejected
    },
)
```

### 6.2 Approve

```
POST /admin/memory/proposals/{id}/approve
```

1. Load proposal. If `metadata.status != 'open'`, 409.
2. Read draft file at `metadata.draft_path`.
3. Compute target dir: `~/.ntrp/skills/<slug>/`. If exists, 409 (skill name collision — user must rename via a query param).
4. Move file: `mv /tmp/ntrp/proposed-skills/<slug>/SKILL.md ~/.ntrp/skills/<slug>/SKILL.md`.
5. Write new `kind=skill` row:
   ```python
   MemoryItem(
       kind="skill",
       scope=proposal.scope,
       content=draft_skill_md,
       tags=["skill"] + topic_tags,
       metadata={
           "skill_slug": slug,
           "skill_path": "~/.ntrp/skills/<slug>/SKILL.md",
           "induced_trigger": trigger,
       },
   )
   ```
6. For each `source_claim_id`: `repo.add_parent(item_id=skill_id, parent_id=claim_id, role='derives_from')`.
7. Update proposal: `metadata.status = 'approved'`, `metadata.approved_at = now`, `metadata.skill_id = skill_id`.
8. Return `{skill_id, skill_path}`.

### 6.3 Reject

```
POST /admin/memory/proposals/{id}/reject
```

1. Load proposal. If `metadata.status != 'open'`, 409.
2. Delete file at `metadata.draft_path` (if exists).
3. Update proposal: `metadata.status = 'rejected'`, `metadata.rejected_at = now`, `metadata.rejection_reason = body.reason` (optional).
4. Return `{rejected_at}`.

### 6.4 List

```
GET /admin/memory/proposals?status=open
```

Returns proposals filtered by status, with their draft SKILL.md content + source-claim count.

---

## 7. Retrieval — `skill_match` reason

`apps/server/ntrp/memory/retrieval.py`: when a `kind=skill` row matches the query (cosine on content embedding OR FTS on trigger phrase), surface with `reason='skill_match'`. ONE branch added; no ranking changes.

---

## 8. Backlog absorption — §2B `test_knowledge_write_gate.py`

Per `slice-07-backlog.md` lines 89-111: 30 tests, file deleted untracked (NOT recoverable). The covered behavior (workflow cluster discovery, write-gate routing, duplicate/conflict routing) is now the proposal flow.

**Re-home action:** write ≥ 10 tests in `test_skill_inducer.py` covering:
- Workflow cluster discovery (was: "Workflow cluster discovery from repeated tool usage")
- Determinism rejection (was: "Workflow cluster candidate body capping" — different shape, same intent: bad candidates don't progress)
- Proposal review markers (was: "Workflow cluster review markers")
- Toolable rejection for unsourced claims (was: "Unsourced/legacy durable candidate routing")
- Duplicate-proposal routing (was: "Duplicate/conflict → review routing")

These count toward the §9 gate of ≥ 15 tests in `test_skill_inducer.py`.

---

## 9. Hard gates

1. `cd apps/server && uv run pytest tests/ --co -q 2>&1 | tail -5` → 0 errors.
2. `cd apps/server && uv run pytest tests/memory/ -q 2>&1 | tail -5` → ≥ 104 passed (81 prior + ≥ 15 inducer + ≥ 8 proposal flow), 0 failed.
3. `cd apps/server && uv run pytest tests/ -q 2>&1 | tail -5` → ≥ 879 passed, 0 failed, 0 xfailed.
4. `cd apps/server && uv run ruff check ntrp/ tests/ 2>&1 | tail -3` → All checks passed!
5. `grep -c 'class SkillInducer\|class IsToolableGate' apps/server/ntrp/memory/skill_inducer.py` → 2
6. `grep -c '^async def test_\|^def test_' apps/server/tests/memory/test_skill_inducer.py` → ≥ 15
7. `grep -c '^async def test_\|^def test_' apps/server/tests/memory/test_proposal_flow.py` → ≥ 8
8. `wc -l apps/server/ntrp/memory/skill_inducer.py` → ≥ 250, ≤ 600
9. `grep -n 'IsToolableGate' apps/server/ntrp/memory/pattern_finder.py` → exactly 2 lines (import + one call site)
10. `ls ~/.ntrp/skills/` BEFORE and AFTER an approve-flow integration test → directory count +1, and the new dir contains SKILL.md
11. `find /tmp/ntrp/proposed-skills/ -name SKILL.md 2>/dev/null | wc -l` after a reject-flow test → 0 (drafts cleaned up)

---

## 10. PM checklist for codex's report

1. Did `tool_sequence` get added cleanly to episode-close metadata? Paste the diff for the episode-close exception.
2. How did you compute `_episode_succeeded`? Heuristic, feedback metadata, or both?
3. What `is_toolable=True` rate did your test fixtures produce? Should match the 5–15% range (too high = gate too loose).
4. List the 10 ported §2B behaviors. Which got dropped entirely?
5. Paste all 11 gate outputs.
6. Did you have to add any new `memory_items` columns or migrations?
7. Did the approve flow correctly mv files OR copy + delete (atomic vs not)? Document.
8. `git diff --stat` vs `main` HEAD.

---

## 11. Codex prompt (verbatim — extracted by invoke.sh §13)

```
You are implementing slice 7 of the ntrp memory redesign — the final pipeline slice.

Prerequisite: slices 5 + 6 landed. Verify with:
  cd apps/server && uv run pytest tests/memory/test_claim_layer.py tests/memory/test_contradictions.py -q

Read `docs/internal/slices/slice-07-skill-inducer.md` start to finish, then:
1. Slice 5 + 6 briefs for prior conventions.
2. `apps/server/ntrp/memory/pattern_finder.py` + `contradictions.py` for hook points.
3. `apps/server/ntrp/memory/retrieval.py` for the `skill_match` reason addition.
4. `docs/internal/ntrp-memory-redesign-spec.md` §3.5 (skill inducer + is_toolable) + §2.5 (skill + proposal kinds).
5. `docs/internal/slices/slice-07-backlog.md` §2B for the ported test behaviors.
6. `~/.ntrp/skills/add-skill/SKILL.md` for the canonical SKILL.md shape.

Implement §1-§8 of the brief. Tests per §9 (≥ 15 inducer + ≥ 8 proposal). Run gates §9. Answer §10.

Frozen zones in §2. The exception in §3.2 (one episode-close metadata field) is the ONLY allowed deviation; document it.

Commit only when all 11 gates green:
  feat(memory): slice 7 — skill inducer + is_toolable gate + proposal flow

Do NOT push. Ask in §10 if ambiguous. This is the slice that completes the memory redesign DoD #2.
```

---

## 12. Sequence of work

1. Read phase: spec §3.5, slice 5+6 briefs, existing SKILL.md examples.
2. `IsToolableGate` skeleton + each of the 4 checks.
3. Episode-close `tool_sequence` addition (the §3.2 exception).
4. `SkillInducer.run` + clustering + LLM SKILL.md drafting.
5. Proposal CRUD endpoints (list, approve, reject) + filesystem moves.
6. `skill_match` retrieval label.
7. `_persist_claim` hook (1 line) for `evaluate_and_tag`.
8. Scheduler registration for `skill-inducer-daily`.
9. Tests (≥ 15 inducer + ≥ 8 proposal flow), including backlog §2B re-homed behaviors.
10. Gates + report.

---

## 13. Sequence of work — codex's plan (aliased for invoke.sh)

(See §12.)

---

## 14. Out of scope explicitly

- **UI for proposals** — separate post-slice-7 UX slice. Slice 7 is API + storage only.
- **Skill execution runtime** — already exists; this slice produces SKILL.md files that the existing loader will pick up.
- **Auto-approval** — non-negotiable per spec §3.5. All proposals require explicit user action.
- **Skill versioning / updates to existing skills** — if a proposal duplicates an existing skill slug, reject with 409; updating existing skills is a follow-up.
- **Cross-scope skill induction** (user-scope skill from project-scope claims) — defer; slice 7 only induces within a single scope.
- **`is_toolable` re-evaluation** when new evidence arrives — once tagged, the value persists until the claim is superseded. Refresh is post-slice-7.

---

## 15. Risk register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| `is_toolable` gate too strict → zero proposals ever produced | Medium | High | Each check has a tunable threshold env var; PM checklist Q3 monitors rate. |
| `is_toolable` gate too loose → noisy proposals | Medium | Medium | Approval gate is the safety net; reject endpoint exists. |
| Filesystem race on approve (file moved twice, parallel approve calls) | Low | High | Approve handler takes an exclusive DB-level lock on the proposal row before fs ops; 409 on second call. |
| `~/.ntrp/skills/` skill slug collision | Medium | Medium | 409 with explicit "rename via ?slug= param" instruction. |
| LLM-drafted SKILL.md hallucinates steps not in evidence | Medium | High | Approval gate; user must read before approving. Logging includes raw evidence link. |
| Episode `tool_sequence` field absent in pre-slice-7 episodes | High | Low | Determinism check returns False with "episodes lack tool_sequence metadata"; only affects historical data, new episodes have it. |
| Test count gate forces shallow tests | Low | Medium | §9 sets minimums; codex can write more. PM checklist Q4 asks about depth. |
| `proposal` kind unrecognized by retrieval until skill exists | Low | Low | Intentional: proposals are not surfaced. Only skills go via `skill_match`. |

---

**End of brief.**
