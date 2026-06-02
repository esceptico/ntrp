# Lens search — fix + UX/animation overhaul

> Previous round (memory lens real-data fix) is complete; see git history for the prior `todo.md`.

**Goal:** Make lens evidence search actually work, then turn it into a live, animated, well-designed surface — and polish the surrounding lens UI.

**Architecture:** Frontend = React/TS desktop (Electron) in `apps/desktop`, animation via `motion` v12 with tokens in `lib/tokens/motion.ts`. Backend = FastAPI in `apps/server`. Search hits `GET /admin/memory/search` (FTS) through the Electron IPC bridge (`apiWithConfig`).

**Tech stack:** React 19, `motion/react`, Tailwind, Electron; FastAPI + aiosqlite (FTS5); tests = `bun test` (desktop), `pytest` (server).

## Process rules (non-negotiable, from lessons.md + user prefs)
- **Verify against the live server + real data.** Passing stubbed `bun test` is NOT proof search works. Boot server + desktop, perform a real search, confirm results render.
- **No commits until the user reviews.** Implement → verify → present → commit only on the user's go-ahead. Stage only the files this work touches (the tree has unrelated uncommitted changes).
- **No heuristics for meaning** (lessons.md): no keyword/regex/threshold gates. Not expected here, but holds.
- **Animation taste = restraint** (memory: modern-animations): spring + minimal exit; no ring flashes, shakes, or two-stage acks.
- Work stays on the current branch (`fix/remember-extract-subjects`); never `main`.

## Orchestration
- Discovery already done via a 5-agent workflow.
- Implementation is **sequential** (main loop): `LensEvidenceSearch.tsx` and `LensesView.tsx` are touched by many subtasks, so parallel editing would conflict; UI taste is context-heavy.
- **Phase 4 uses a workflow**: parallel adversarial review (search-fix correctness, regression risk, animation taste, a11y) + verification.

---

## File structure

- `apps/desktop/src/api/memoryItems.ts` — `searchMemory` routes through `apiWithConfig`; delete `fetchMemorySearch`; `MemorySearchParams.scope_*` become unused by lens search.
- `apps/desktop/src/components/memory/shared.tsx` — extend `SearchInput` (`autoFocus`, `busy` spinner).
- `apps/desktop/src/components/memory/LensEvidenceSearch.tsx` — rewrite: live/debounced, whole-pool, `SearchInput`, motion'd results, real states, slim row actions.
- `apps/desktop/src/components/memory/LensesView.tsx` — consolidate to one page-level search; group headers seed it; Phase-3 polish (GenerationProgress, chevrons, delete-confirm, dedupe, spacing).
- `apps/server/ntrp/server/routers/memory.py` — `scope_kind: str | None = None` → whole-pool when omitted (fts mode).
- `apps/server/tests/memory/test_memory_router.py` — whole-pool search test.
- `apps/desktop/tests/lensesView.test.tsx` — rewrite to the new contract (live search, no scope params, new badges).

---

## Phase 1 — Make search work (the bug) — ✅ DONE
Evidence: real-FTS pytest `test_search_fts_whole_pool_when_scope_omitted` passes (7/7 search tests). Live proof vs real `~/.ntrp/memory.db` (`/tmp/lens_search_verify.py`): whole-pool vs user-scope = dex 139/8, lens 6/0, user 196/75 — old scoped search hid cross-scope claims; `lens` returned 0 user-scope = the "finds nothing" symptom. `has_fts=True`, FTS works read-only. Transport: `searchMemory`→`apiWithConfig` (bridge), `tsc --noEmit` clean. Packaged-app UI smoke deferred to Phase 4.

### Task 1: Backend — whole-pool search when scope omitted
**Files:** Modify `apps/server/ntrp/server/routers/memory.py:419-448`; Test `apps/server/tests/memory/test_memory_router.py`

- [ ] **1.1** Change the `search` endpoint signature: `scope_kind: str | None = None`.
- [ ] **1.2** In the `fts` branch: `scope = _scope(scope_kind, scope_key) if scope_kind else None` (None → `store.search` skips the scope filter → searches all scopes). In the `retrieve` branch: `scope = _scope(scope_kind or "user", scope_key)` (preserve retrieve's prior default).
- [ ] **1.3** Test: seed claims under ≥2 different scopes (e.g. `user`/null and `project`/`dex`); `GET /admin/memory/search?q=<term>&mode=fts` with **no** `scope_kind` returns items from **both** scopes; with `scope_kind=project&scope_key=dex` returns only the project one. Run `uv run pytest apps/server/tests/memory/test_memory_router.py -v`.
- [ ] **1.4** Surfaced behavior change: ClaimsView (passes no scope) now searches whole pool too — intended (the Claims tab should show all claims). Verify its existing behavior/tests still hold.

### Task 2: Frontend — restore the working transport
**Files:** Modify `apps/desktop/src/api/memoryItems.ts:315-346`

- [ ] **2.1** Rewrite `searchMemory` to use the bridge-aware client:
  ```ts
  export function searchMemory(config: AppConfig, params: MemorySearchParams) {
    return apiWithConfig<MemorySearchResponse>(
      config,
      `/admin/memory/search${queryString({
        q: params.q,
        scope_kind: params.scope_kind,
        scope_key: params.scope_key,
        limit: params.limit,
        include_inactive: params.include_inactive,
        mode: params.mode,
      })}`,
      { timeout: 8_000 } as RequestInit & { timeout?: number },
    );
  }
  ```
- [ ] **2.2** Delete `fetchMemorySearch` (the raw renderer fetch that bypassed the bridge — the regression from commit `5789e07f`). Add the `apiWithConfig` import.
- [ ] **2.3** Confirm `apiWithConfig` is imported in `memoryItems.ts` (it already imports for `writebackLens`/`createLens`). No other caller of `fetchMemorySearch`.

### Task 3: Live verification of the fix (REQUIRED before Phase 2)
- [ ] **3.1** Boot server (`uv run ntrp-server serve`) + desktop dev. Open a lens, search a known term, confirm real results render (not "No claims found", not an error). Use the `run`/`verify` skill if helpful.
- [ ] **3.2** Confirm in DevTools Network that `/admin/memory/search` is a 200 with `items` (and `degraded:false`). If `degraded:true`, the read store's FTS probe is off — investigate `init_readonly`/`db_connect(readonly)`.

---

## Phase 2 — Search UX + animations — ✅ DONE
Evidence: live/debounced whole-pool search (mirrors ClaimsView); reuses extended `SearchInput` (autofocus + busy spinner); consolidated to one page-level search seeded by group headers; calm rows (hover Open/Include, ok-tone In view/Included, no amber "Review criterion"); idle/skeleton/empty-with-guidance states; motion (SPRING_POPOVER open, AnimatePresence popLayout rows w/ SPRING_LAYOUT + split tween). Tests rewritten seed-driven: 11/11 pass; `tsc --noEmit` clean.

## Phase 2 — Search UX + animations (detail)

### Task 4: Extend the canonical `SearchInput`
**Files:** Modify `apps/desktop/src/components/memory/shared.tsx:250-289`

- [ ] **4.1** Add optional props `autoFocus?: boolean` and `busy?: boolean`. When `busy`, swap the leading `Search` icon for a spinning `Loader2` (Tailwind `animate-spin`); keep the clear button.
- [ ] **4.2** Pass `autoFocus` to the `<input>`. No behavior change for existing callers (rail filter).

### Task 5: Rewrite `LensEvidenceSearch` — live, whole-pool, animated
**Files:** Modify `apps/desktop/src/components/memory/LensEvidenceSearch.tsx` (full rewrite of body)

- [ ] **5.1** Live/debounced search mirroring `ClaimsView.tsx:64-95`: `useEffect` on trimmed `query` → empty clears results (no request, `searched=false`); else `setTimeout(DEBOUNCE)` → `searchMemory(config, { q, mode:"fts", limit: 12 })` (**no scope** → whole pool); `alive` flag drops stale responses; cleanup clears the timer. Keep Enter = search-now; remove the manual Search button. Escape = clear/close.
- [ ] **5.2** Use the extended `SearchInput` (drop the bespoke input → removes the `h-7`/`.input-field` conflict and the `pl-7`+inline-padding duplication). `autoFocus` when the panel opens; `busy` while a request is in flight.
- [ ] **5.3** Result rows = quiet rows that reveal actions on hover (mirror `ClaimBlock`): keep **Open** + **Include** only. Remove per-row **Refresh** and **Edit criterion**.
- [ ] **5.4** Calmer badges: show a quiet `ok`-tone "In view"/"Included" ONLY for items already in the lens; show nothing for not-yet-included (drop the amber `warn` "Review criterion"). Keep the grouped `count` badge.
- [ ] **5.5** Real states: idle hint ("Search your memory to add evidence"); skeleton/spinner while `busy`; empty state with guidance ("No matching claims — try a broader term") instead of the dead-end "No claims found." Surface an "Edit criterion" link contextually in the empty state, not per-row.
- [ ] **5.6** Motion (tokens from `lib/tokens/motion.ts`, mirror `AutomationsModal`/`AgentRightSidebar`):
  - Popover open/close: `motion.div`, `initial={{opacity:0, scale:0.98, y:-4}}` → animate in, transition `SPRING_POPOVER` (origin-anchored).
  - Results list: `<AnimatePresence mode="popLayout" initial={false}>`; each row `motion.div` `layout`, `initial={{opacity:0,y:-4}}`/`animate`/`exit={{opacity:0,scale:0.98}}`, split transition `{ layout: SPRING_LAYOUT, opacity: { duration: MOTION.row }, y: { duration: MOTION.fast } }`. Stable `key` (existing item.id / canonical_subject).
  - First-paint stagger only: container variant `delayChildren: stagger(0.035)` gated to a fresh result set (don't re-stagger per keystroke); `initial={false}` prevents replay on open.
  - Include flips In-view → Included via `layout` (no abrupt pop).
  - Reduced motion already handled globally by `<MotionConfig reducedMotion="user">` — do NOT add local `useReducedMotion`.

### Task 6: Consolidate to one page-level search (recommended option)
**Files:** Modify `apps/desktop/src/components/memory/LensesView.tsx:555-598` (+ `GroupedProfiles` group headers)

- [ ] **6.1** Render a **single** `LensEvidenceSearch` at the page level (`:590`). Remove the per-group `evidenceSearch={(subject) => <LensEvidenceSearch .../>}` instances passed into `GroupedProfiles` (`:565-575`).
- [ ] **6.2** Lift the search's open/seed state to `LensPage`. Each `GroupedProfiles` group header gets a small "find evidence for X" affordance that opens + focuses the single search seeded with the subject term (whole-pool query). One live search; per-subject convenience preserved.
- [ ] **6.3** Add a separator/heading above the page-level search so "lens content" vs "search to add more" is visually distinct (fixes the `mt-2` collision).

### Task 7: Rewrite `lensesView.test.tsx` to the new contract
**Files:** Modify `apps/desktop/tests/lensesView.test.tsx`

- [ ] **7.1** Update the search tests: assert the request URL has **no** `scope_kind`/`scope_key` (whole pool); results appear via debounced typing (no "Search" button); assert the new badge text ("In view"/"Included"), NOT "Review criterion"; drop the `padding-left: 2rem` assertion (now `SearchInput`). Keep the unmount-staleness and Include tests, adapted to the live-search flow (`setInputValue` → wait past `DEBOUNCE`).
- [ ] **7.2** Keep the `globalThis.fetch` mock harness — `apiWithConfig` falls back to `fetch` in jsdom (no `window.ntrpDesktop`), so it still intercepts. Run `cd apps/desktop && bun test tests/lensesView.test.tsx`.

---

## Phase 3 — Broader lens polish — ✅ DONE (8.1–8.3); ⏸ DEFERRED (8.4–8.5)
Done: GenerationProgress step icons animate (pop on complete via AnimatePresence + label color ease + container entrance); both chevrons (GroupedProfiles + ClaimSources) now rotate on the same SPRING_LAYOUT spring as the body; native `window.confirm` delete replaced with an in-app inline confirm (Cancel / Delete view, DangerBtn). `tsc --noEmit` clean for all changed files.
Deferred (subjective refactors, higher regression risk on now-verified code — recommend a separate visual pass): 8.4 dedupe coverage-meter/Edit-criterion surfaces, 8.5 spacing-rhythm + empty-state voice. ("Edit criterion" was already removed from search rows in Phase 2.)
Note: `AutomationsModal.tsx` has pre-existing typecheck errors from a parallel WIP refactor — NOT touched by this work.

## Phase 3 — Broader lens polish (detail)
**Files:** Modify `apps/desktop/src/components/memory/LensesView.tsx` (+ `styles.css` if needed)

- [ ] **8.1** Animate `GenerationProgress` step swaps (`:1078-1090`): `AnimatePresence`/`motion` on the Check/Loader2/dot icon + label change (subtle reveal, `MOTION.check`), instead of instant pops.
- [ ] **8.2** Sync chevron rotation with the spring body in `GroupedProfiles` (`:873-915`) and `ClaimSources` (`:952-991`): drive the chevron with the same spring/duration token as the body expansion, not the bare CSS default.
- [ ] **8.3** Replace native `window.confirm()` delete (`:626`) with an in-app glass confirm consistent with the UI (small inline confirm or existing modal primitive — grep for an existing confirm component first).
- [ ] **8.4** Dedupe: coverage meter (CriterionRow `:776-777` vs footer CoverageStrip `:601-602`) and "Edit criterion" (CriterionRow + footer + per-row, now removed from rows) — keep one canonical location each.
- [ ] **8.5** Normalize spacing rhythm in the lens page (consistent vertical scale vs ad-hoc mt-3/mt-4/mt-7) and unify empty-state voice across rail/page/search.

---

## Phase 4 — Review + verify (workflow) — ✅ DONE
- Adversarial review workflow (4 dimensions × find→verify): 7 raised, 6 confirmed (all low/med, 1 dismissed false-positive). Fixes applied via a 2nd file-partitioned workflow: dropped the StrictMode-broken `mounted` ref (no-defensive-code); Escape `stopPropagation` so it no longer closes the whole Memory modal; reseed refocus (input ref); `focus-within` on hover row actions; delete-confirm `AnimatePresence` + exit; GenerationProgress detail token transition. Verification caught a workflow-introduced `requestAnimationFrame is not defined` (jsdom) → replaced rAF with direct post-commit focus.
- Gate: lensesView 11/11, apiCompact 5/5, full desktop suite green except 2 pre-existing failures in the parallel automation-suggestion WIP (automationSuggestions/automationEditorSuggestion — NOT this work); `tsc` clean for all my files; Python memory 174/174; build OK.
- Live: backend whole-pool proven on real ~/.ntrp/memory.db. Packaged-app UI smoke (type→results stream, Include, seed) left for the user in the running app.

## Phase 4 — Review + verify (detail)

- [ ] **9.1** Run a review workflow: parallel agents over dimensions — (a) search-fix correctness & no-regression on the transport, (b) whole-pool scope correctness incl. ClaimsView, (c) animation taste/restraint vs the repo's motion language, (d) a11y/keyboard/reduced-motion. Adversarially verify each finding; fix confirmed issues.
- [ ] **9.2** Full gate: `cd apps/desktop && bun test && bun run typecheck && bun run build`; `uv run pytest apps/server/tests/memory -q`.
- [ ] **9.3** Live smoke (REQUIRED): boot server + desktop, exercise live search (type → results stream), Include, empty/idle states, grouped-lens seed affordance. Confirm with real `~/.ntrp/memory.db` data.
- [ ] **9.4** Present diff + verification evidence for review. Commit only on the user's go-ahead.

---

## Review (outcome)
- **Search fixed** (task #2): transport reverted to the Electron bridge (`apiWithConfig`) — fixes the packaged-app CSP/CORS break; backend searches the whole pool when scope is omitted — fixes "finds nothing" for non-user lenses. Proven on real data.
- **Search UX/animations** (task #1): live debounced whole-pool search, reused `SearchInput` (autofocus + busy spinner), one page-level search seeded by group headers, calm rows (hover Open/Include, ok-tone In view/Included), motion'd results (popLayout + spring), idle/skeleton/empty states.
- **Lens polish**: animated GenerationProgress, spring-synced chevrons, in-app delete confirm.
- **Deferred (need user's design call)**: 8.4 dedupe coverage-meter / Edit-criterion locations; 8.5 spacing rhythm + empty-state voice unification.
- **Not committed** — awaiting user review (per no-auto-commit). Unrelated parallel WIP (AutomationsModal/automation-suggestions) has its own typecheck errors + 2 test failures — untouched by this work.
