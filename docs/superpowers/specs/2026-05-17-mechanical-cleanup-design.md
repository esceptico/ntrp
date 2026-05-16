# Mechanical Cleanup Pass — Design

**Date:** 2026-05-17
**Scope:** Desktop Electron app at `apps/desktop/`.
**Type:** Pure refactor. No new product behavior.

## Purpose

A component-audit pass surfaced nine categories of duplication and dead code. This spec covers only the **mechanical** subset — items where the change is local, the API decision is settled, and no design tradeoffs remain. Larger structural extractions (ContextMenu, Chip, ListRow/StatusCard, settings tab split-ups) get their own specs.

## Tasks

### 1. Promote `MCPTab.tsx` local `Field` as `LabeledField`

**Problem.** `apps/desktop/src/components/settings/MCPTab.tsx:737` defines a local `Field` function that collides in name with the shared `apps/desktop/src/components/settings/Field.tsx`'s `Field` export. The two have different APIs:

- Shared `Field` — labeled text input. Props: `label, value, onChange, placeholder, help, type`.
- MCPTab local `Field` — label wraps caller-provided children. Props: `label, children`.

They are not duplicates; they answer different needs. The name collision is the only problem.

**Change.**

1. Add `export function LabeledField({ label, children }: { label: string; children: ReactNode })` to `apps/desktop/src/components/settings/Field.tsx`. Behavior matches the MCPTab local implementation verbatim:
   ```tsx
   <label className="grid gap-1.5">
     <span className="text-sm font-medium tracking-[-0.005em] text-ink-soft">{label}</span>
     {children}
   </label>
   ```
2. Delete the local `Field` function from `MCPTab.tsx`.
3. Import `LabeledField` in `MCPTab.tsx` and replace every `<Field` call site inside that file with `<LabeledField`.

**Verification.** `bun run typecheck` clean. Visual regression check: open any MCP server form in the Settings modal; field labels render unchanged.

---

### 2. Move `useTimeTicker` to `lib/hooks.ts`

**Problem.** `Sidebar.tsx:16-22` defines a generic time-ticker hook that forces re-renders on a fixed interval. Belongs in `lib/hooks.ts` (which already hosts `useTimeoutFlag` and similar utilities).

**Change.**

1. Cut the function body from `Sidebar.tsx:16-22`.
2. Paste into `apps/desktop/src/lib/hooks.ts` with `export`.
3. `Sidebar.tsx` imports it from `../lib/hooks`.

No API change.

---

### 3. Move `useOutsideClick` to `lib/hooks.ts`

**Problem.** `ComposerSelectors.tsx:25-39` exports a generic outside-click hook. Lives in a component file because that's where it was first needed. Promoting it unblocks any future dropdown/popover work.

**Change.**

1. Cut the function from `ComposerSelectors.tsx:25-39`.
2. Paste into `apps/desktop/src/lib/hooks.ts` with `export`.
3. `ComposerSelectors.tsx` imports it from `../lib/hooks`.
4. Grep the codebase for any other file importing `useOutsideClick` from `ComposerSelectors`; update each importer to point at `lib/hooks` instead.

No API change.

---

### 4. Generalize `useAutomationsPoll` → `useVisibilityPoll`

**Problem.** `Sidebar.tsx:642-660` defines `useAutomationsPoll` which directly calls `fetchAutomations`. The hook's shape — invoke callback on mount, on each interval tick (when visible), and on visibility transition back to visible — is fully generic. The hardcoded dependency on `fetchAutomations` makes the hook un-reusable.

**Change.**

1. Add to `apps/desktop/src/lib/hooks.ts`:
   ```ts
   export function useVisibilityPoll(
     callback: () => void | Promise<void>,
     intervalMs: number,
   ): void
   ```
   Semantics:
   - On mount: invoke `callback()` once.
   - Set an interval (`setInterval`, `intervalMs`). Each tick: invoke `callback()` only when `document.visibilityState === "visible"`.
   - On `visibilitychange` events: when transitioning to `"visible"`, invoke `callback()`.
   - On unmount: clear the interval and remove the listener. Also set a `cancelled` flag so any in-flight async callback skips its post-resolve work.
   - The hook captures the latest `callback` via a ref so consumers don't have to memoize.

2. In `Sidebar.tsx`, replace `useAutomationsPoll()` with `useVisibilityPoll(fetchAutomations, 20_000)`. Delete the old `useAutomationsPoll` function.

**Verification.** Manual: open the app, switch to another window for >20s, switch back — sidebar automations list should refresh on focus. Sidebar should also refresh on its 20s tick while focused.

---

### 5. Delete `GlassSurface.tsx`

**Problem.** Zero importers across `apps/desktop/src/`. The component is a typed wrapper that maps props to glass CSS classes; every consumer writes the classes inline instead. Dead code.

**Change.** `rm apps/desktop/src/components/GlassSurface.tsx`.

**Verification.** `bun run typecheck` clean (proves no surviving import).

---

### 6. Delete `trace/Demo.tsx` and its hash branch

**Problem.** `apps/desktop/src/components/trace/Demo.tsx` is a dev-only playground for iterating on the activity trace component. Reachable only by visiting the app with `#trace-demo` in the URL hash. Not product code.

**Change.**

1. `rm apps/desktop/src/components/trace/Demo.tsx`.
2. `apps/desktop/src/components/App.tsx`: remove the import at line 12 (`import { Demo as TraceDemo } from "./trace/Demo";`) and the early-return branch at lines 152-154 (`if (hash === "#trace-demo") return <TraceDemo />;`).

**Verification.** `bun run typecheck` clean. App still loads normally on the default route.

---

## Order

Tasks are independent. Sequential execution via subagent-driven-development for review discipline. Suggested order:

1. Task 5 (delete `GlassSurface.tsx`) — smallest, mechanical.
2. Task 6 (delete `trace/Demo.tsx`) — small, two-file touch.
3. Task 1 (promote `LabeledField`) — single-file refactor.
4. Task 2 (move `useTimeTicker`) — two-file move.
5. Task 3 (move `useOutsideClick`) — two-file move + grep.
6. Task 4 (generalize `useVisibilityPoll`) — design touch on a hook; needs the most attention.

## Out of scope

- Other dedup categories from the audit (ContextMenu, Chip, ListRow / ListSection / StatusCard, settings tab split-ups, form editors out of MCPTab, status-indicator unification). Each is its own spec.
- Renaming MCPTab's other local helpers (`Empty`, `AddBtn`, `RemoveBtn`). Those are local patterns; promote only when a second consumer needs them.
- The `GlassSurface` typed-wrapper question — whether to revive it as the canonical glass API. Out of scope here; deletion is final for this pass.

## Verification across all tasks

After every task and at the end:

```sh
cd apps/desktop && bun run typecheck
```

Must exit clean with no `tsc` errors.

No automated test suite for these components exists. Visual sanity check: open the app after the full pass, verify the MCP form, sidebar polling, and any other touched surfaces still behave normally.
