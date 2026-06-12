# Task-Result Toasts & Shared Tabs Primitive

**Date:** 2026-06-01
**Status:** Approved (design), pending implementation plan
**Surface:** `apps/desktop` (React desktop app)

## Motivation

Reuse vetted motion.dev interaction patterns to (a) fill a genuine gap and (b)
consolidate hand-rolled UI. After mapping the eight candidate patterns against
the existing codebase, only two survive as net-positive: most of the rest are
already solved well (`RollingToken` odometer, `TurnGroup`/`ActivityTrace`
collapse, `ApprovalBanner`/`QueueCard` decks) and replacing them would churn
working code.

The two adopted patterns:

1. **Shared Tabs primitive** with a sliding underline indicator — replaces three
   inconsistent, static tab implementations.
2. **Task-result toasts** — a missing in-app notification surface for background
   and scheduled work that finishes while the user is looking elsewhere.

Cross-cutting rule: every lifted snippet is rewired to the existing motion
tokens in `apps/desktop/src/lib/tokens/motion.ts` (`SPRING_*`, `EASE_*`,
`MOTION.*`). No inline `transition={{ ... }}` literals from motion.dev — that
would fork the timing language.

## Out of Scope (explicit)

- Error / system-warning toasts
- Mirroring backend notifier (Telegram/email) events in-app
- Manual action-feedback toasts (copied/saved/archived)
- Stacking hard-cap (toasts stack unbounded — see Risk below)
- Failure-persistence (failures auto-dismiss like successes)
- The other six motion.dev candidates (accordion, number-trend, dots-morph
  button, skeleton shimmer, scroll-track-in-viewport)

---

## Part 1 — Shared Tabs Primitive (dual-variant)

### Goal

One reusable `<Tabs>` primitive whose active indicator **slides** between tabs
via motion shared-layout. Reading the three target surfaces showed they are NOT
all underline tab rows — they use three different shapes, so the primitive must
support two indicator variants and two orientations:

| Surface | Shape today | Variant / orientation |
|---|---|---|
| `AutomationsModal` | Horizontal row, static 2px underline + count badges | `underline`, horizontal |
| `MemoryItemsPane` | `flex-wrap` row of filled pills, two-line (label + hint) | `pill`, horizontal (wraps) |
| `SettingsModal` | Vertical icon sidebar, active = filled background | `pill`, vertical |

A single sliding-underline primitive would not fit a vertical sidebar or a
wrapping two-line pill row, so the primitive is built dual-variant from the
start. This is what earns the abstraction across all three.

### Component

`apps/desktop/src/components/ui/Tabs.tsx` — a compound component.

```
<Tabs value={active} onChange={setActive} variant="underline" orientation="horizontal">
  <Tab value="active">Active <Badge/></Tab>
  <Tab value="channels">Channels</Tab>
</Tabs>
```

- Props: `value`, `onChange`, `variant: "underline" | "pill"`,
  `orientation: "horizontal" | "vertical"` (default horizontal),
  `className` for the nav container. `<Tab value>` takes arbitrary children
  (label, icon, badge, two-line content) so each surface keeps its exact
  content/styling.
- The active indicator is a `motion.div` with a `layoutId` **unique per Tabs
  instance** (derived from React `useId()`, so multiple Tabs mounted at once —
  e.g. settings sidebar plus another modal — don't share a layout group).
  - `underline`: absolutely-positioned 2px bar at the bottom edge of the active
    tab (`bg-ink rounded-full`).
  - `pill`: absolutely-positioned inset background behind the active tab's
    content (`bg-surface-soft` + inset ring), `z` below the label.
- Animated with `SPRING_LAYOUT` — consistent with `RollingToken`/`TurnGroup`
  shared-layout usage.
- Respects reduced motion: when `useReducedMotion()` is true, the indicator
  jumps (no `layout` transition) instead of sliding.
- `<Tab>` renders a `<button type="button">`; the indicator is injected by the
  primitive. Panel content stays with the caller (Tabs owns selection
  presentation only).

### Migration

Replace the bespoke tab markup in all three surfaces with `<Tabs>`/`<Tab>`,
preserving each surface's existing content (badges in Automations, icon+label in
Settings sidebar, two-line label+hint in Memory) and passing the matching
`variant`/`orientation`. Delete the per-surface indicator markup
(`AutomationsModal`'s `TabButton` underline span, `MemoryItemsPane`'s
`bg-surface-soft` active classes, `SettingsModal`'s sidebar `data-active`
indicator). No backend, no new dependencies.

### Testing

- Indicator lands on the active tab on mount, slides on change, and is present
  exactly once per Tabs instance.
- `underline` vs `pill` variant each render their indicator element.
- `prefers-reduced-motion` → indicator positions without a slide transition.
- Each migrated surface still switches panels and preserves badges/icons/hints.

---

## Part 2 — Task-Result Toasts

### Goal

Show a top-right toast when a **background agent** or **scheduled automation**
reaches a terminal state while the user is looking at a different part of the
app. Clicking the toast jumps to the relevant session/automation.

### Existing infrastructure (no backend/transport work needed)

Both signals already reach the client:

- **Scheduled automations** → `automation_finished` event (`{ task_id, result }`)
  on the global `/automations/events` SSE stream, handled in
  `apps/desktop/src/hooks/useAutomationEvents.ts`.
- **Background agents** → `background_task` events with terminal `status`
  (`completed` / `failed` / `cancelled`) on the per-session chat stream, already
  upserted into the Zustand store (`store/chat-stream.ts`) and rendered in
  `AgentRightSidebar`. Payload carries `task_id`, `session_id`, `command`,
  `status`, `detail`, `result_ref`.

The gap is purely presentational: nothing currently turns a terminal transition
into a notification.

### Architecture (chosen approach: general primitive + focused watcher)

Three small pieces:

1. **`apps/desktop/src/store/toast.ts`** — Zustand slice.
   - State: `toasts: Toast[]`
   - Actions: `pushToast(toast)`, `dismissToast(id)`
   - Auto-dismiss timer (~5s, uniform for success and failure) lives in the
     slice. `Toast = { id, title, status, target }` where `status` is
     `completed | failed | cancelled` and `target` describes where a click
     navigates (session id or automation id).

2. **`apps/desktop/src/hooks/useTaskResultToasts.ts`** — the single watcher.
   - Subscribes to terminal transitions of `store.backgroundAgents`
     (running → completed/failed/cancelled) and to `automation_finished`.
   - Builds a toast and calls `pushToast`.
   - **Suppression:** skips the toast when `target` matches the currently
     focused session/automation (the "already in view" rule) — this honors the
     "while you're elsewhere" intent.
   - **Dedupe:** keyed on task id so a re-render cannot double-fire a toast for
     the same terminal transition.
   - This is the *only* place task-result trigger logic lives.

3. **`apps/desktop/src/components/Toaster.tsx`** — fixed top-right container.
   - Renders the toast stack with `AnimatePresence` (motion.dev `base-toast`
     pattern, rewired to tokens): enter/exit on `MOTION.panel` +
     `EASE_DECELERATE`; layout reflow on `SPRING_LAYOUT`.
   - Each toast: title, status glyph, click-to-jump (navigates to `target`,
     then dismisses). Auto-dismiss after ~5s; manual dismiss available.
   - Mounted once in `App.tsx`. Anchored top-right (clear of the bottom
     composer; OS-notification convention).

### Data flow

```
existing SSE  →  existing store upsert  →  useTaskResultToasts detects
terminal transition  →  pushToast  →  <Toaster> renders  →  click routes
to session/automation
```

Nothing new on the wire; no changes to backend, SSE endpoints, or event
payloads.

### Behavior summary (decisions)

| Behavior                  | Decision                                            |
|---------------------------|-----------------------------------------------------|
| Triggers                  | Background agent terminal + scheduled automation finished |
| Anchor                    | Top-right                                           |
| Click                     | Jump to relevant session/automation, then dismiss   |
| Suppress if in view       | Yes — skip when target is currently focused          |
| Auto-dismiss              | Uniform ~5s for success and failure                  |
| Stacking                  | Vertical stack, no hard cap                          |

### Risk

No stacking cap: a burst of simultaneous terminal completions could stack many
toasts in the corner. Mitigated in practice by suppression (focused source is
skipped) and auto-dismiss (each clears in ~5s). If this proves noisy in use, a
soft cap (~3 visible, older ones collapse) is a follow-up — not built now.

### Testing

- `useTaskResultToasts`: terminal transition pushes exactly one toast; repeated
  store updates for the same task do not duplicate; suppression skips a toast
  when the target is the focused source.
- `store/toast.ts`: auto-dismiss removes the toast after the timeout;
  `dismissToast` removes immediately.
- `Toaster`: renders the stack, enter/exit animates, click invokes navigation
  and dismiss, respects `prefers-reduced-motion`.

---

## Files

**New**
- `apps/desktop/src/components/ui/Tabs.tsx`
- `apps/desktop/src/store/toast.ts`
- `apps/desktop/src/hooks/useTaskResultToasts.ts`
- `apps/desktop/src/components/Toaster.tsx`

**Modified**
- `apps/desktop/src/components/SettingsModal.tsx` (use `<Tabs variant="pill" orientation="vertical">`)
- `apps/desktop/src/components/AutomationsModal.tsx` (use `<Tabs variant="underline">`)
- `apps/desktop/src/components/memory/MemoryItemsPane.tsx` (use `<Tabs variant="pill">`)
- `apps/desktop/src/components/App.tsx` (mount `<Toaster>`, run `useTaskResultToasts`)

**No changes**
- Backend, SSE endpoints, event payloads, `lib/tokens/motion.ts`
