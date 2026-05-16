# Mechanical Cleanup Pass — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete two dead files, move three hooks to `lib/hooks.ts` (generalizing one), and resolve one component name collision in the desktop Electron app — purely structural cleanup, no behavior change.

**Architecture:** Six independent tasks against `apps/desktop/`. No new abstractions; only consolidation of code that already exists. Each task touches 1–2 files and is verified by `bun run typecheck` plus, where relevant, a one-line manual check.

**Tech Stack:** TypeScript, React 19, Bun (typecheck via `tsc --noEmit`), Tailwind CSS v4.

**Spec:** `docs/superpowers/specs/2026-05-17-mechanical-cleanup-design.md`

---

## Task 1: Delete `GlassSurface.tsx`

**Files:**
- Delete: `apps/desktop/src/components/GlassSurface.tsx`

- [ ] **Step 1: Verify zero importers**

Run: `grep -rn "from .*GlassSurface" apps/desktop/src/ 2>/dev/null`
Expected: empty output (no matches).

If any match appears, STOP and report. Do not proceed.

- [ ] **Step 2: Delete the file**

Run: `rm apps/desktop/src/components/GlassSurface.tsx`

- [ ] **Step 3: Typecheck**

Run: `cd apps/desktop && bun run typecheck`
Expected: exits clean (no errors).

- [ ] **Step 4: Commit**

```bash
git add -A apps/desktop/src/components/
git commit -m "Delete GlassSurface — zero importers"
```

---

## Task 2: Delete `trace/Demo.tsx` and its hash branch

**Files:**
- Delete: `apps/desktop/src/components/trace/Demo.tsx`
- Modify: `apps/desktop/src/components/App.tsx` (remove import + early-return branch)

- [ ] **Step 1: Delete the file**

Run: `rm apps/desktop/src/components/trace/Demo.tsx`

- [ ] **Step 2: Remove import from `App.tsx`**

Edit `apps/desktop/src/components/App.tsx`. Remove the line:

```tsx
import { Demo as TraceDemo } from "./trace/Demo";
```

(It is line 12 at the time of writing — verify by searching for `TraceDemo` and removing the import.)

- [ ] **Step 3: Remove the hash branch from `App.tsx`**

In the same file, locate the early-return block that reads:

```tsx
if (hash === "#trace-demo") {
  return <TraceDemo />;
}
```

Delete those 3 lines.

- [ ] **Step 4: Verify no `TraceDemo` / `trace/Demo` references remain**

Run: `grep -rn "TraceDemo\|trace/Demo" apps/desktop/src/`
Expected: empty output.

- [ ] **Step 5: Typecheck**

Run: `cd apps/desktop && bun run typecheck`
Expected: exits clean.

- [ ] **Step 6: Commit**

```bash
git add -A apps/desktop/src/components/
git commit -m "Delete trace/Demo dev playground"
```

---

## Task 3: Promote MCPTab's local `Field` as `LabeledField`

**Files:**
- Modify: `apps/desktop/src/components/settings/Field.tsx` (add new export)
- Modify: `apps/desktop/src/components/settings/MCPTab.tsx` (delete local Field, import LabeledField, rename 6 call sites)

- [ ] **Step 1: Add `LabeledField` export to `settings/Field.tsx`**

Append to `apps/desktop/src/components/settings/Field.tsx`:

```tsx
/** Wraps a caller-provided control with a label. Use when the control
 *  isn't a plain text input (a select, a toggle group, a custom editor). */
export function LabeledField({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="grid gap-1.5">
      <span className="text-sm font-medium tracking-[-0.005em] text-ink-soft">{label}</span>
      {children}
    </label>
  );
}
```

(If `React` is not already imported in the file, add `import type { ReactNode } from "react";` and use `ReactNode` instead of `React.ReactNode`.)

- [ ] **Step 2: Verify the file compiles**

Run: `cd apps/desktop && bun run typecheck`
Expected: exits clean.

- [ ] **Step 3: Delete the local `Field` function in `MCPTab.tsx`**

In `apps/desktop/src/components/settings/MCPTab.tsx`, find this block (around line 737):

```tsx
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="grid gap-1.5">
      <span className="text-sm font-medium tracking-[-0.005em] text-ink-soft">{label}</span>
      {children}
    </label>
  );
}
```

Delete it entirely.

- [ ] **Step 4: Add the `LabeledField` import to `MCPTab.tsx`**

In the import block at the top of `MCPTab.tsx`, add (or extend the existing import from `./Field` if one already exists):

```tsx
import { LabeledField } from "./Field";
```

- [ ] **Step 5: Rename all `<Field` call sites in `MCPTab.tsx`**

There are 6 call sites at lines 362, 562, 573, 583, 603, 614 (verify by searching `<Field` within the file). For each, replace:

```
<Field label="...">
...
</Field>
```

with:

```
<LabeledField label="...">
...
</LabeledField>
```

- [ ] **Step 6: Verify no surviving `<Field>` calls in MCPTab**

Run: `grep -n "<Field" apps/desktop/src/components/settings/MCPTab.tsx`
Expected: empty output.

- [ ] **Step 7: Typecheck**

Run: `cd apps/desktop && bun run typecheck`
Expected: exits clean.

- [ ] **Step 8: Commit**

```bash
git add apps/desktop/src/components/settings/Field.tsx apps/desktop/src/components/settings/MCPTab.tsx
git commit -m "Promote MCPTab local Field as settings/LabeledField"
```

---

## Task 4: Move `useTimeTicker` to `lib/hooks.ts`

**Files:**
- Modify: `apps/desktop/src/lib/hooks.ts` (add export)
- Modify: `apps/desktop/src/components/Sidebar.tsx` (delete local, add import)

- [ ] **Step 1: Add `useTimeTicker` to `lib/hooks.ts`**

Append to `apps/desktop/src/lib/hooks.ts`:

```ts
/** Forces a re-render every `intervalMs` ms. Use to refresh relative-time
 *  labels ("2m ago") without each consumer wiring its own timer. */
export function useTimeTicker(intervalMs = 30_000): void {
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((n) => n + 1), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
}
```

(Verify `useState` and `useEffect` are already imported at the top of `lib/hooks.ts` — they are. No new imports needed.)

- [ ] **Step 2: Delete `useTimeTicker` from `Sidebar.tsx`**

In `apps/desktop/src/components/Sidebar.tsx`, find this block (around line 16):

```tsx
function useTimeTicker(intervalMs = 30_000): void {
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((n) => n + 1), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
}
```

Delete it entirely.

- [ ] **Step 3: Add the import in `Sidebar.tsx`**

In the existing `import { ... } from "../lib/hooks";` line (if present) add `useTimeTicker`. If no such import exists yet, add:

```tsx
import { useTimeTicker } from "../lib/hooks";
```

next to the other `../lib/...` imports in the file's import block.

- [ ] **Step 4: Verify `useState` / `useEffect` are still needed in Sidebar.tsx**

`Sidebar.tsx` may still use these from `react`. Leave the existing `react` import alone. Only remove `useState` or `useEffect` from the import if no other code in the file references them (likely they're still used — check with `grep -n "useState\|useEffect" apps/desktop/src/components/Sidebar.tsx`).

- [ ] **Step 5: Typecheck**

Run: `cd apps/desktop && bun run typecheck`
Expected: exits clean.

- [ ] **Step 6: Commit**

```bash
git add apps/desktop/src/lib/hooks.ts apps/desktop/src/components/Sidebar.tsx
git commit -m "Move useTimeTicker to lib/hooks"
```

---

## Task 5: Move `useOutsideClick` to `lib/hooks.ts`

**Files:**
- Modify: `apps/desktop/src/lib/hooks.ts` (add export)
- Modify: `apps/desktop/src/components/ComposerSelectors.tsx` (delete local, add import)

(Audit confirms `useOutsideClick` has no importers other than `ComposerSelectors` itself, so no other files need updating.)

- [ ] **Step 1: Add `useOutsideClick` to `lib/hooks.ts`**

Append to `apps/desktop/src/lib/hooks.ts`:

```ts
/** Calls `onClose` when a `mousedown` lands outside the element referenced
 *  by `ref`. No-op when `open` is false (keeps the listener off when it
 *  isn't needed). Used by popovers, dropdowns, and command pickers. */
export function useOutsideClick(
  ref: RefObject<HTMLElement | null>,
  open: boolean,
  onClose: () => void,
): void {
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open, ref, onClose]);
}
```

(`RefObject` is already imported at the top of `lib/hooks.ts` — verify with `grep "RefObject" apps/desktop/src/lib/hooks.ts`. If not, add `type RefObject` to the existing `import { ... } from "react";`.)

- [ ] **Step 2: Delete `useOutsideClick` from `ComposerSelectors.tsx`**

In `apps/desktop/src/components/ComposerSelectors.tsx`, find this exported function (around line 25) and delete it:

```tsx
export function useOutsideClick(
  ref: React.RefObject<HTMLElement | null>,
  open: boolean,
  onClose: () => void,
) {
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open, ref, onClose]);
}
```

- [ ] **Step 3: Add the import in `ComposerSelectors.tsx`**

Add (or extend existing `../lib/hooks` import to include) `useOutsideClick`:

```tsx
import { useOutsideClick } from "../lib/hooks";
```

- [ ] **Step 4: Verify no surviving local `useOutsideClick` reference in ComposerSelectors**

Run: `grep -n "function useOutsideClick" apps/desktop/src/components/ComposerSelectors.tsx`
Expected: empty output.

- [ ] **Step 5: Verify no other file imports `useOutsideClick` from ComposerSelectors**

Run: `grep -rn "from .*ComposerSelectors.*useOutsideClick\|useOutsideClick.*from.*ComposerSelectors" apps/desktop/src/`
Expected: empty output. If anything appears, update those imports to point to `../lib/hooks` instead.

- [ ] **Step 6: Typecheck**

Run: `cd apps/desktop && bun run typecheck`
Expected: exits clean.

- [ ] **Step 7: Commit**

```bash
git add apps/desktop/src/lib/hooks.ts apps/desktop/src/components/ComposerSelectors.tsx
git commit -m "Move useOutsideClick to lib/hooks"
```

---

## Task 6: Generalize `useAutomationsPoll` → `useVisibilityPoll`

**Files:**
- Modify: `apps/desktop/src/lib/hooks.ts` (add `useVisibilityPoll` export)
- Modify: `apps/desktop/src/components/Sidebar.tsx` (delete `useAutomationsPoll`, call `useVisibilityPoll` instead)

- [ ] **Step 1: Add `useVisibilityPoll` to `lib/hooks.ts`**

Append to `apps/desktop/src/lib/hooks.ts`:

```ts
/** Invokes `callback` once on mount, then on each `intervalMs` tick
 *  (skipped when the document is hidden), and again on every visibility
 *  transition back to "visible". The latest `callback` is captured in a
 *  ref so consumers don't need to memoize it.
 *
 *  Use for background data refresh that should pause when the user
 *  switches away from the window (saves API calls, respects user focus). */
export function useVisibilityPoll(
  callback: () => void | Promise<void>,
  intervalMs: number,
): void {
  const cbRef = useRef(callback);
  cbRef.current = callback;
  useEffect(() => {
    let cancelled = false;
    const tick = () => {
      if (!cancelled) void cbRef.current();
    };
    tick();
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") tick();
    }, intervalMs);
    const onVis = () => {
      if (document.visibilityState === "visible") tick();
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      cancelled = true;
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [intervalMs]);
}
```

(`useRef` should already be imported in `lib/hooks.ts` — verify with `grep "useRef" apps/desktop/src/lib/hooks.ts`. If not, add it to the existing `react` import.)

- [ ] **Step 2: Delete `useAutomationsPoll` from `Sidebar.tsx`**

In `apps/desktop/src/components/Sidebar.tsx`, find this block (around line 642) and delete it entirely:

```tsx
function useAutomationsPoll(): void {
  useEffect(() => {
    let cancelled = false;
    const tick = () => { if (!cancelled) void fetchAutomations(); };
    tick();
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") tick();
    }, 20_000);
    const onVis = () => { if (document.visibilityState === "visible") tick(); };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      cancelled = true;
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, []);
}
```

- [ ] **Step 3: Replace the call site in `Sidebar.tsx`**

Inside the `Sidebar` component body (near where `useAutomationsPoll()` was previously called), replace:

```tsx
useAutomationsPoll();
```

with:

```tsx
useVisibilityPoll(fetchAutomations, 20_000);
```

If there is no existing call to `useAutomationsPoll` because it was removed in Step 2, search the file for `useAutomationsPoll` to find any remaining caller, replace each, then delete the now-unused name.

- [ ] **Step 4: Add the import in `Sidebar.tsx`**

Extend the existing `../lib/hooks` import (added in Task 4) to include `useVisibilityPoll`:

```tsx
import { useTimeTicker, useVisibilityPoll } from "../lib/hooks";
```

(`fetchAutomations` is already imported by `Sidebar.tsx` — confirm with `grep "fetchAutomations" apps/desktop/src/components/Sidebar.tsx`.)

- [ ] **Step 5: Verify no surviving `useAutomationsPoll` reference**

Run: `grep -rn "useAutomationsPoll" apps/desktop/src/`
Expected: empty output.

- [ ] **Step 6: Typecheck**

Run: `cd apps/desktop && bun run typecheck`
Expected: exits clean.

- [ ] **Step 7: Manual verification**

Start the desktop app. Open it, switch to another window for ~25 seconds (longer than the 20 s tick), switch back. The sidebar's "Active agents / automations" list should refresh on focus (visibility-change handler) AND continue ticking every 20 s while the window is focused.

- [ ] **Step 8: Commit**

```bash
git add apps/desktop/src/lib/hooks.ts apps/desktop/src/components/Sidebar.tsx
git commit -m "Generalize useAutomationsPoll into useVisibilityPoll(callback, intervalMs)"
```

---

## Final pass

- [ ] **Step 1: Full-codebase typecheck**

Run: `cd apps/desktop && bun run typecheck`
Expected: exits clean.

- [ ] **Step 2: Sanity grep for known-deleted names**

Run:

```sh
grep -rn "GlassSurface\|TraceDemo\|useAutomationsPoll" apps/desktop/src/
```

Expected: empty output.

- [ ] **Step 3: Manual smoke**

Open the desktop app. Verify:
- Settings → MCP tab → "Add server": form fields render with labels (LabeledField working).
- Sidebar: session timestamps update (useTimeTicker working).
- Composer: model picker opens and closes when clicking outside (useOutsideClick working).
- Sidebar: leave the window unfocused for 25 s, refocus — active agents/automations refresh (useVisibilityPoll working).
