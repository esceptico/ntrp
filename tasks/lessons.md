# Lessons

## Subagent = first-class session; don't band-aid with polling (Jun 2026)

I "fixed" no-live-updates-in-subagent-sessions with a 2s poll-refresh of the viewed child session (`useViewedAgentSessionRefresh` + `appendLatestForSession`). User: "not correct — subagent must look and work the same as default agent, no differences."

Root: subagent events emit to the PARENT bus (foreground shares `calling_ctx.io`) / a throwaway `IOBridge` (background); the child session's own `SessionBus` is never fed, so `/chat/events/{childSessionId}` is silent → the viewed child is static. A poll is a special-case band-aid that makes subagents second-class.

Rule: when a subagent/child concept already maps onto an existing first-class primitive (a session), stream it through the SAME machinery (its own bus + the normal `useEvents` path), not a parallel poll. Ties to [[feedback_no_special_casing_fit_general_primitives]]. Correct fix: route the child agent's events to its OWN session bus at **depth 0** (the desktop hard-gates `!event.depth`, so depth-1 events render blank/orphaned); the parent gets ONLY lifecycle (it treats session-backed agents as trace leaves). Non-obvious trap: bus idle-eviction is keyed on `get_active_run(session_id)` — a child session has no RunState, so navigating away mid-run silently evicts + recreates its bus with reset seq (replay drift); needs a lightweight active-session marker.

## React StrictMode: `useRef(true)` + cleanup-only-false "mounted" gate is broken in dev (Jun 2026)

`const mounted = useRef(true); useEffect(() => () => { mounted.current = false; }, [])` is unsafe under `<StrictMode>` (enabled in src/main.tsx). Dev runs mount effects setup→cleanup→setup; the cleanup flips it false and the empty setup never restores true, so the ref is stuck `false` for the component's whole life in dev — every `if (mounted.current)` gate becomes a permanent no-op (stuck spinners, errors never shown, busy never clears). Bit twice: `LensEvidenceSearch`'s `mounted` and the shared `useMountedRef` hook (feeding `useMutationState`).

Rule: prefer DROPPING the gate — setState-after-unmount is a harmless no-op in React 18/19 (the warning that motivated these guards was removed in React 18), so a mounted-gate that only protects setState is pure defensive code (no-defensive-code stance). Only if a gate is genuinely load-bearing (guards a side effect, not setState) set `ref.current = true` at the START of the effect body (the LensPage pattern), never cleanup-only. Audit before deleting a shared hook: grep all callers and confirm none use the ref for a side-effect guard.

## "use /workflows" means orchestrate the implementation too (Jun 2026)

On the lens-search task I used workflows for discovery + adversarial review but implemented the actual changes solo in the main loop (reasoning LensEvidenceSearch.tsx / LensesView.tsx overlapped too much for parallel agents). User: "next time use /workflows please."

Rule: when the user asks to use /workflows, decompose the **implementation** across workflow agents — `isolation: "worktree"` for overlapping-file parallel edits, or `pipeline()`/`parallel()` partitioned by file/area for independent ones — not just the research/review bracket. Solo main-loop editing only for trivial or tightly-coupled single-file changes.

## Memory work — the spec IS the implementation guide; read it FIRST, every time (Jun 2026)

Before ANY memory decision (diagnosis, fix, build, answer), read the governing docs FIRST — never improvise then check:
- `~/vault/Memory Consolidation/Memory — vision (new spec).md` (the model)
- `~/vault/Memory Consolidation/Lens — spec.md` (lenses)
- `tasks/memory-rebuild.md`, `tasks/lens-view-correction.md` (what was built / locked)

Cost of not doing this: I proposed routing `remember()` through Extract (user had explicitly said "remember is just a tool, no logic") and missed that the built lens layer (single `people` lens grouping by `canonical_subject`) DIVERGES from the spec, which says **entity = lens, membership by LLM scoring** (Lens spec §4). Two wrong fixes in a row because I reasoned from code + memory instead of the spec.

Rule: the spec is the source of truth. Read it before forming any opinion. If code diverges from spec, the divergence is the bug — don't rationalize the code.

## Memory rebuild — no hard-rule/lexical heuristics (Jun 2026)

Build/workflow agents repeatedly smuggle lexical heuristics in despite "no heuristic gate" — Stage 3 baked them into the CONTRACT and multiple components: `_PRONOUN_HINTS = {"i","me","user",...}` (reconcile subject recall), `_PROPER_NOUN_RE` regex + `_STOPWORD_CAPS` (extract), and a contract-level "Pronoun/role channel (deterministic)".

Rule: **every decision AND every recall channel is LLM/embedding/FTS — never a hand-maintained word list, keyword set, or regex-for-meaning.** Subject/coreference identity comes from the LLM resolving a canonical subject at extract time + embedding/FTS recall + LLM judge — not a pronoun list. (English-only word lists are also brittle/non-general.)

Prevention: workflow build prompts MUST say this explicitly (not just "no opaque gate"); a verify step MUST grep the pipeline for `frozenset`/`_WORDS`/`_TERMS`/`_HINTS`/`re.compile`/keyword-`in {`-sets and fail on any decision/recall use. Watch capture's idle/time boundary — a mechanical chunking trigger is OK; a *semantic* gate is not.

## Lens page: don't make the model reproduce opaque ids; don't block the GET on synthesis (Jun 2026)

Two coupled bugs shipped because the test stub was too friendly:

1. **Raw-list fallback fired on every faithful render.** `project.py` required the synthesizer to echo `<!--claim:ID-->` anchors verbatim and fell back to raw bullets if any were missing. Real models drop opaque ids (lessons above), so the page was never the synthesized markdown. Fix: the model cites claims by the numbered `[n]` tag it was given (it never sees the id); the projector injects anchors deterministically post-synthesis (`_inject_anchors`, index→id substitution — structural, not a heuristic). Raw fallback now means genuine failure only (blank output / cites no claim at all).

2. **The page GET ran multi-call synthesis synchronously and timed out.** Membership refresh + re-validate + one strong-model synthesis per subject = 6–14s on the request path. Fix: `LensPageGenerator.ensure` — cache hit returns the page (200); miss/dirty/refresh starts ONE deduped background `asyncio.create_task` and returns a `generating` status (HTTP 202); the projector reports stage/subject/i-n progress through a callback; a `/page/status` endpoint is the UI poll target. New fast-path `LensProjector.cached_page()` reads the materialized page with zero synthesis/judge.

Anti-stub testing rule (this is WHY the bugs hid): the existing tests passed with a stub that echoed anchors instantly. New tests MUST defeat that — a synth stub that cites by `[n]` and provably emits NO `<!--claim:` (prove injection, not echo), and a GATED/slow synth stub awaited via `httpx.ASGITransport` (so the route's background task runs in the test loop) to prove the GET returns 202 fast and never blocks. A `TestClient` runs its own loop in a worker thread and orphans the `create_task`, so use `AsyncClient(ASGITransport)` + `gen.drain()` when asserting background completion.


## Design-system tokens (May 2026)

### @property registration is required to transition CSS custom properties
A bare `--my-var: 0.3` declared in `:root` is a *string* to the browser — CSS
transitions on it snap rather than interpolate. To get smooth easing across
custom props (e.g. glass rim alpha drifting on hover), declare them with
`@property` so the browser knows the syntax/type:

```css
@property --rim-alpha {
  syntax: "<number>";
  inherits: true;
  initial-value: 0.18;
}
```

Bit us in Phase 5 of the tokens migration — the rim drift looked like a step
function until we registered the prop.

### Token migration: ship aliases first, retire later
When renaming or restructuring tokens (motion, color, elevation) across a large
component surface, the discipline that kept each phase reviewable was:

1. Land the new token module alongside the old one — re-export the old name as
   a back-compat alias from the new module.
2. Sweep call sites to the new name in a follow-up phase.
3. Delete the alias only in a final cleanup phase, after `tsc --noEmit` confirms
   zero remaining importers.

This keeps each commit small and bisectable. Trying to rename + sweep + delete
in one pass forces every consumer through review at once and makes the diff
unreadable. Phase 4 (color) deferred its alias-retirement entirely because
per-palette `:root.palette-*` blocks still override the defaults — aliases are
load-bearing until a separate palette-block sweep lands.
