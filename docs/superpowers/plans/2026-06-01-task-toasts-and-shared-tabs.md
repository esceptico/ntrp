# Task-Result Toasts & Shared Tabs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add in-app toasts for background/scheduled task results, and a dual-variant sliding-indicator `<Tabs>` primitive that replaces three hand-rolled tab UIs.

**Architecture:** Two independent tracks. (1) Toasts: a pure decision helper (`lib/taskToast.ts`) + a toast slice on the existing Zustand store + a `<Toaster>` view + a watcher hook for background agents + one call site for scheduled automations. All trigger events already reach the client — this is presentation + wiring only. (2) Tabs: a compound `<Tabs>/<Tab>` component whose active indicator slides via motion `layoutId`, supporting `underline`/`pill` variants and horizontal/vertical orientation.

**Tech Stack:** React, `motion/react` (v12), Zustand, Tailwind v4, `bun:test` + `renderToStaticMarkup` (no RTL/jsdom).

**Spec:** `docs/superpowers/specs/2026-06-01-task-toasts-and-shared-tabs-design.md`

**Conventions observed:**
- Tests live in `apps/desktop/tests/*.test.ts(x)`, import from `../src/...` with explicit `.ts`/`.tsx` extensions, run with `bun test <path>` from `apps/desktop`.
- Component tests assert on `renderToStaticMarkup(...)` HTML strings. Store/helper tests call functions directly and assert via `getState()/setState()` from `../src/store/index.ts`.
- Motion tokens live in `src/lib/tokens/motion.ts`. Never inline raw spring/duration literals.
- The app is already wrapped in `<MotionConfig reducedMotion="user">` in `App.tsx`.

All paths below are relative to `apps/desktop/`.

---

## File Structure

**New**
- `src/lib/taskToast.ts` — `Toast`/`ToastTarget` types, `isTerminalStatus`, pure builders `backgroundAgentToast` / `automationToast`. One responsibility: decide whether/what to toast. No React, no store.
- `src/components/Toaster.tsx` — top-right toast stack view + per-toast auto-dismiss + click-to-jump. One responsibility: render toasts.
- `src/hooks/useTaskResultToasts.ts` — watches `backgroundAgents.rows` for terminal transitions, pushes toasts. One responsibility: background-agent trigger.
- `src/components/ui/Tabs.tsx` — `<Tabs>/<Tab>` compound primitive with sliding indicator. One responsibility: tab selection presentation.
- `tests/taskToast.test.ts`, `tests/toastStore.test.ts`, `tests/tabs.test.tsx` — unit tests.

**Modified**
- `src/store/types.ts` — add `toasts` to `State`, `pushToast`/`dismissToast` to `Actions`.
- `src/store/index.ts` — add `toasts: []` initial state + the two actions.
- `src/hooks/useAutomationEvents.ts` — on `automation_finished`, build + push a toast.
- `src/components/App.tsx` — call `useTaskResultToasts()`, mount `<Toaster/>`.
- `src/components/AutomationsModal.tsx` — migrate to `<Tabs variant="underline">`, delete local `TabButton`.
- `src/components/memory/MemoryItemsPane.tsx` — migrate to `<Tabs variant="pill">`.
- `src/components/SettingsModal.tsx` — migrate sidebar to `<Tabs variant="pill" orientation="vertical">`.

---

## TRACK A — Toasts

### Task 1: Toast model + pure decision helpers

**Files:**
- Create: `src/lib/taskToast.ts`
- Test: `tests/taskToast.test.ts`

- [ ] **Step 1: Write the failing test**

```tsx
// tests/taskToast.test.ts
import { expect, test } from "bun:test";
import {
  automationToast,
  backgroundAgentToast,
  isTerminalStatus,
} from "../src/lib/taskToast.ts";
import type { BackgroundAgent } from "../src/store/background-agent-domain.ts";

const agent = (over: Partial<BackgroundAgent> = {}): BackgroundAgent => ({
  taskId: "t1",
  sessionId: "s1",
  command: "build the thing",
  status: "completed",
  createdAt: 0,
  updatedAt: 1,
  ...over,
});

test("isTerminalStatus only matches completed/failed/cancelled", () => {
  expect(isTerminalStatus("completed")).toBe(true);
  expect(isTerminalStatus("failed")).toBe(true);
  expect(isTerminalStatus("cancelled")).toBe(true);
  expect(isTerminalStatus("running")).toBe(false);
  expect(isTerminalStatus("interrupted")).toBe(false);
});

test("backgroundAgentToast: terminal + not focused → session-targeted toast", () => {
  const toast = backgroundAgentToast(agent(), "other-session");
  expect(toast).not.toBeNull();
  expect(toast?.id).toBe("bg:s1:t1");
  expect(toast?.title).toBe("build the thing");
  expect(toast?.status).toBe("completed");
  expect(toast?.target).toEqual({ kind: "session", sessionId: "s1" });
});

test("backgroundAgentToast: suppressed when its session is focused", () => {
  expect(backgroundAgentToast(agent({ sessionId: "s1" }), "s1")).toBeNull();
});

test("backgroundAgentToast: non-terminal → null", () => {
  expect(backgroundAgentToast(agent({ status: "running" }), "x")).toBeNull();
});

test("automationToast: builds an automation-targeted toast", () => {
  const toast = automationToast({
    taskId: "a1",
    name: "Daily digest",
    result: "3 items",
    automationsOpen: false,
  });
  expect(toast?.id).toBe("auto:a1");
  expect(toast?.title).toBe("Daily digest");
  expect(toast?.detail).toBe("3 items");
  expect(toast?.target).toEqual({ kind: "automation" });
});

test("automationToast: falls back to a generic title; suppressed when modal open", () => {
  expect(
    automationToast({ taskId: "a1", name: null, result: null, automationsOpen: false })?.title,
  ).toBe("Scheduled task");
  expect(
    automationToast({ taskId: "a1", name: "X", result: null, automationsOpen: true }),
  ).toBeNull();
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `bun test tests/taskToast.test.ts`
Expected: FAIL — `Cannot find module "../src/lib/taskToast.ts"`.

- [ ] **Step 3: Write the implementation**

```ts
// src/lib/taskToast.ts
import type { BackgroundAgent } from "../store/background-agent-domain";

export type ToastStatus = "completed" | "failed" | "cancelled";

export type ToastTarget =
  | { kind: "session"; sessionId: string }
  | { kind: "automation" };

export interface Toast {
  id: string;
  title: string;
  detail?: string;
  status: ToastStatus;
  target: ToastTarget;
}

export function isTerminalStatus(status: string): status is ToastStatus {
  return status === "completed" || status === "failed" || status === "cancelled";
}

/** Toast for a background agent that reached a terminal state. Returns null
 *  when it is not terminal, or when the user is already looking at its session
 *  (suppress redundant noise). */
export function backgroundAgentToast(
  agent: BackgroundAgent,
  currentSessionId: string | null,
): Toast | null {
  if (!isTerminalStatus(agent.status)) return null;
  if (agent.sessionId === currentSessionId) return null;
  return {
    id: `bg:${agent.sessionId}:${agent.taskId}`,
    title: agent.command || "Background task",
    detail: agent.detail,
    status: agent.status,
    target: { kind: "session", sessionId: agent.sessionId },
  };
}

/** Toast for a finished scheduled automation. Returns null when the automations
 *  modal is open (the user is already looking at it). */
export function automationToast(args: {
  taskId: string;
  name: string | null;
  result: string | null;
  automationsOpen: boolean;
}): Toast | null {
  if (args.automationsOpen) return null;
  return {
    id: `auto:${args.taskId}`,
    title: args.name ?? "Scheduled task",
    detail: args.result ?? undefined,
    status: "completed",
    target: { kind: "automation" },
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `bun test tests/taskToast.test.ts`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/lib/taskToast.ts apps/desktop/tests/taskToast.test.ts
git commit -m "feat(desktop): toast model + pure task-result decision helpers"
```

---

### Task 2: Toast store slice

**Files:**
- Modify: `src/store/types.ts` (add to `State` and `Actions`)
- Modify: `src/store/index.ts` (initial state + actions, inside the single `create()`)
- Test: `tests/toastStore.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// tests/toastStore.test.ts
import { beforeEach, expect, test } from "bun:test";
import { getState, setState } from "../src/store/index.ts";
import type { Toast } from "../src/lib/taskToast.ts";

const toast = (id: string): Toast => ({
  id,
  title: "Done",
  status: "completed",
  target: { kind: "automation" },
});

beforeEach(() => setState({ toasts: [] }));

test("pushToast appends a toast", () => {
  getState().pushToast(toast("x"));
  expect(getState().toasts.map((t) => t.id)).toEqual(["x"]);
});

test("pushToast ignores a duplicate id", () => {
  getState().pushToast(toast("x"));
  getState().pushToast(toast("x"));
  expect(getState().toasts.length).toBe(1);
});

test("dismissToast removes by id", () => {
  getState().pushToast(toast("x"));
  getState().pushToast(toast("y"));
  getState().dismissToast("x");
  expect(getState().toasts.map((t) => t.id)).toEqual(["y"]);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `bun test tests/toastStore.test.ts`
Expected: FAIL — `getState().pushToast is not a function`.

- [ ] **Step 3: Add the types**

In `src/store/types.ts`, add an import near the other type imports:

```ts
import type { Toast } from "../lib/taskToast";
```

Add to the `State` interface (next to `currentSessionId` or other UI state fields):

```ts
  toasts: Toast[];
```

Add to the `Actions` interface (next to `automationFinished`):

```ts
  pushToast: (toast: Toast) => void;
  dismissToast: (id: string) => void;
```

- [ ] **Step 4: Add the initial state + actions**

In `src/store/index.ts`, add to the initial state object (next to other UI state, e.g. near `backgroundAgents`):

```ts
  toasts: [],
```

Add the actions inside the same `create()` callback (next to `automationFinished`):

```ts
  pushToast: (toast) =>
    set((s) => (s.toasts.some((t) => t.id === toast.id) ? {} : { toasts: [...s.toasts, toast] })),
  dismissToast: (id) =>
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `bun test tests/toastStore.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 6: Typecheck**

Run: `cd apps/desktop && bun run tsc --noEmit` (or the project's typecheck script if different — check `package.json`).
Expected: no new type errors.

- [ ] **Step 7: Commit**

```bash
git add apps/desktop/src/store/types.ts apps/desktop/src/store/index.ts apps/desktop/tests/toastStore.test.ts
git commit -m "feat(desktop): toast slice on the store (pushToast/dismissToast)"
```

---

### Task 3: Toaster view component

**Files:**
- Create: `src/components/Toaster.tsx`

No unit test (interaction/visual, and the project has no DOM-event test harness). Verified via typecheck here and manual run in Task 6.

- [ ] **Step 1: Write the component**

```tsx
// src/components/Toaster.tsx
import { useEffect } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Check, Slash, X } from "lucide-react";
import { useStore } from "../store";
import { switchSession } from "../actions";
import { EASE_DECELERATE, MOTION, SPRING_LAYOUT } from "../lib/tokens/motion";
import { ICON } from "../lib/icons";
import type { Toast } from "../lib/taskToast";

const DISMISS_MS = 5000;
const STATUS_ICON = { completed: Check, failed: X, cancelled: Slash } as const;

export function Toaster() {
  const toasts = useStore((s) => s.toasts);
  return (
    <div className="fixed top-3 right-3 z-50 flex w-[min(360px,calc(100vw-24px))] flex-col gap-2 pointer-events-none">
      <AnimatePresence initial={false}>
        {toasts.map((toast) => (
          <ToastCard key={toast.id} toast={toast} />
        ))}
      </AnimatePresence>
    </div>
  );
}

function ToastCard({ toast }: { toast: Toast }) {
  const dismissToast = useStore((s) => s.dismissToast);
  const openAutomations = useStore((s) => s.openAutomations);
  const Icon = STATUS_ICON[toast.status];

  useEffect(() => {
    const timer = setTimeout(() => dismissToast(toast.id), DISMISS_MS);
    return () => clearTimeout(timer);
  }, [toast.id, dismissToast]);

  function onClick() {
    if (toast.target.kind === "session") void switchSession(toast.target.sessionId);
    else openAutomations();
    dismissToast(toast.id);
  }

  return (
    <motion.button
      type="button"
      layout
      onClick={onClick}
      initial={{ opacity: 0, y: -8, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -8, scale: 0.97 }}
      transition={{ layout: SPRING_LAYOUT, duration: MOTION.panel, ease: EASE_DECELERATE }}
      data-toast-status={toast.status}
      className="glass-surface glass-radius-md pointer-events-auto flex w-full items-start gap-2.5 px-3.5 py-3 text-left"
    >
      <span className="mt-0.5 grid h-4 w-4 shrink-0 place-items-center text-ink-soft">
        <Icon size={ICON.SM} strokeWidth={2} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium text-ink">{toast.title}</span>
        {toast.detail && (
          <span className="block truncate text-2xs text-muted">{toast.detail}</span>
        )}
      </span>
    </motion.button>
  );
}
```

> If `glass-surface`/`glass-radius-md`/`text-ink-soft`/`text-2xs`/`ICON.SM` don't resolve, confirm exact names against an existing overlay (e.g. `CompactionIndicator.tsx`, `PageModal.tsx`) and adjust — these are existing project tokens.

- [ ] **Step 2: Typecheck**

Run: `cd apps/desktop && bun run tsc --noEmit`
Expected: no new type errors.

- [ ] **Step 3: Commit**

```bash
git add apps/desktop/src/components/Toaster.tsx
git commit -m "feat(desktop): Toaster view — top-right stack, auto-dismiss, click-to-jump"
```

---

### Task 4: Background-agent watcher hook

**Files:**
- Create: `src/hooks/useTaskResultToasts.ts`

- [ ] **Step 1: Write the hook**

```tsx
// src/hooks/useTaskResultToasts.ts
import { useEffect, useRef } from "react";
import { useStore } from "../store";
import { backgroundAgentToast, isTerminalStatus } from "../lib/taskToast";

/** Watches background agents for terminal transitions and raises a toast the
 *  first time each one finishes. Scheduled-automation toasts are raised from
 *  useAutomationEvents (that is where their event arrives). */
export function useTaskResultToasts() {
  const rows = useStore((s) => s.backgroundAgents.rows);
  const currentSessionId = useStore((s) => s.currentSessionId);
  const pushToast = useStore((s) => s.pushToast);
  const seen = useRef<Set<string>>(new Set());

  useEffect(() => {
    for (const agent of Object.values(rows)) {
      const key = `bg:${agent.sessionId}:${agent.taskId}`;
      if (!isTerminalStatus(agent.status) || seen.current.has(key)) continue;
      seen.current.add(key); // mark even if suppressed, so it cannot re-fire later
      const toast = backgroundAgentToast(agent, currentSessionId);
      if (toast) pushToast(toast);
    }
  }, [rows, currentSessionId, pushToast]);
}
```

- [ ] **Step 2: Typecheck**

Run: `cd apps/desktop && bun run tsc --noEmit`
Expected: no new type errors. (`backgroundAgents.rows` is `Record<string, BackgroundAgent>`; `currentSessionId` is `string | null` — both already in the store.)

- [ ] **Step 3: Commit**

```bash
git add apps/desktop/src/hooks/useTaskResultToasts.ts
git commit -m "feat(desktop): useTaskResultToasts — toast on background-agent completion"
```

---

### Task 5: Wire scheduled-automation toasts

**Files:**
- Modify: `src/hooks/useAutomationEvents.ts` (the `automation_finished` branch, ~line 116)

- [ ] **Step 1: Add the import**

At the top of `src/hooks/useAutomationEvents.ts`, add:

```ts
import { automationToast } from "../lib/taskToast";
```

- [ ] **Step 2: Push the toast on finish**

Find the existing handler:

```ts
                } else if (event.type === "automation_finished") {
                  store().automationFinished(event.task_id);
```

Replace it with:

```ts
                } else if (event.type === "automation_finished") {
                  store().automationFinished(event.task_id);
                  const st = store();
                  const auto = st.automations?.find((a) => a.task_id === event.task_id) ?? null;
                  const toast = automationToast({
                    taskId: event.task_id,
                    name: auto?.name ?? null,
                    result: event.result,
                    automationsOpen: st.automationsOpen,
                  });
                  if (toast) st.pushToast(toast);
```

> `store()` is the getState accessor already used in this file (see the `automationProgress`/`automationFinished` calls). `automations` (`Automation[] | null`), `automationsOpen` (`boolean`), and `pushToast` are all on the store. `Automation.task_id` matches the event's `task_id`, and `Automation.name` is the display title.

- [ ] **Step 3: Typecheck**

Run: `cd apps/desktop && bun run tsc --noEmit`
Expected: no new type errors.

- [ ] **Step 4: Commit**

```bash
git add apps/desktop/src/hooks/useAutomationEvents.ts
git commit -m "feat(desktop): raise a toast when a scheduled automation finishes"
```

---

### Task 6: Mount Toaster + watcher in App

**Files:**
- Modify: `src/components/App.tsx`

- [ ] **Step 1: Add imports**

Near the other component/hook imports in `src/components/App.tsx`:

```ts
import { Toaster } from "./Toaster";
import { useTaskResultToasts } from "../hooks/useTaskResultToasts";
```

- [ ] **Step 2: Call the hook**

Inside `export function App() { ... }`, alongside the other top-level hook calls (before the `return`):

```ts
  useTaskResultToasts();
```

- [ ] **Step 3: Mount the Toaster**

In the returned JSX, add `<Toaster />` as a sibling overlay just after `<ApprovalReviewModal />` (still inside `<MotionConfig>`):

```tsx
      <ApprovalReviewModal />
      <Toaster />
    </MotionConfig>
```

- [ ] **Step 4: Typecheck**

Run: `cd apps/desktop && bun run tsc --noEmit`
Expected: no new type errors.

- [ ] **Step 5: Manual verification**

Start the desktop app (per project run instructions). Trigger a background agent or scheduled automation while viewing a different session, and confirm a toast appears top-right, auto-dismisses after ~5s, and clicking it navigates to the session / opens the automations modal. Confirm no toast appears when you are already viewing that session.

- [ ] **Step 6: Commit**

```bash
git add apps/desktop/src/components/App.tsx
git commit -m "feat(desktop): mount Toaster and run task-result watcher in App"
```

---

## TRACK B — Tabs primitive

### Task 7: `<Tabs>` / `<Tab>` primitive

**Files:**
- Create: `src/components/ui/Tabs.tsx`
- Test: `tests/tabs.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// tests/tabs.test.tsx
import { expect, test } from "bun:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Tab, Tabs } from "../src/components/ui/Tabs.tsx";

test("renders a button per tab and marks the active one", () => {
  const html = renderToStaticMarkup(
    <Tabs value="b" onChange={() => {}} variant="underline">
      <Tab value="a">Alpha</Tab>
      <Tab value="b">Beta</Tab>
    </Tabs>,
  );
  expect(html).toContain("Alpha");
  expect(html).toContain("Beta");
  expect(html).toContain('role="tablist"');
  expect((html.match(/role="tab"/g) ?? []).length).toBe(2);
  expect(html).toContain('aria-selected="true"');
});

test("underline variant renders exactly one underline indicator", () => {
  const html = renderToStaticMarkup(
    <Tabs value="a" onChange={() => {}} variant="underline">
      <Tab value="a">Alpha</Tab>
      <Tab value="b">Beta</Tab>
    </Tabs>,
  );
  expect((html.match(/data-tab-indicator/g) ?? []).length).toBe(1);
  expect(html).toContain('data-tab-indicator="underline"');
});

test("pill variant renders a pill indicator with the supplied indicator class", () => {
  const html = renderToStaticMarkup(
    <Tabs
      value="a"
      onChange={() => {}}
      variant="pill"
      indicatorClassName="indicator-probe"
    >
      <Tab value="a">Alpha</Tab>
    </Tabs>,
  );
  expect(html).toContain('data-tab-indicator="pill"');
  expect(html).toContain("indicator-probe");
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `bun test tests/tabs.test.tsx`
Expected: FAIL — `Cannot find module "../src/components/ui/Tabs.tsx"`.

- [ ] **Step 3: Write the implementation**

```tsx
// src/components/ui/Tabs.tsx
import { createContext, useContext, useId, type ReactNode } from "react";
import { motion, useReducedMotion } from "motion/react";
import clsx from "clsx";
import { SPRING_LAYOUT } from "../../lib/tokens/motion";

type Variant = "underline" | "pill";
type Orientation = "horizontal" | "vertical";

interface TabsContextValue {
  value: string;
  onChange: (value: string) => void;
  variant: Variant;
  orientation: Orientation;
  layoutId: string;
  indicatorClassName?: string;
  reduced: boolean;
}

const TabsContext = createContext<TabsContextValue | null>(null);

function useTabsContext(): TabsContextValue {
  const ctx = useContext(TabsContext);
  if (!ctx) throw new Error("<Tab> must be used inside <Tabs>");
  return ctx;
}

export function Tabs({
  value,
  onChange,
  variant = "underline",
  orientation = "horizontal",
  indicatorClassName,
  className,
  children,
}: {
  value: string;
  onChange: (value: string) => void;
  variant?: Variant;
  orientation?: Orientation;
  indicatorClassName?: string;
  className?: string;
  children: ReactNode;
}) {
  const layoutId = useId();
  const reduced = !!useReducedMotion();
  return (
    <TabsContext.Provider
      value={{ value, onChange, variant, orientation, layoutId, indicatorClassName, reduced }}
    >
      <div
        role="tablist"
        aria-orientation={orientation}
        className={clsx("flex", orientation === "vertical" && "flex-col", className)}
      >
        {children}
      </div>
    </TabsContext.Provider>
  );
}

export function Tab({
  value,
  className,
  children,
}: {
  value: string;
  className?: string;
  children: ReactNode;
}) {
  const ctx = useTabsContext();
  const active = ctx.value === value;
  const transition = ctx.reduced ? { layout: { duration: 0 } } : { layout: SPRING_LAYOUT };

  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      data-active={active ? "true" : undefined}
      onClick={() => ctx.onChange(value)}
      className={clsx("group relative", className)}
    >
      {active && ctx.variant === "pill" && (
        <motion.span
          layoutId={`${ctx.layoutId}-indicator`}
          data-tab-indicator="pill"
          transition={transition}
          className={clsx(
            "absolute inset-0 -z-10 rounded-lg",
            ctx.indicatorClassName ??
              "bg-surface-soft shadow-[inset_0_0_0_1px_var(--color-line-soft)]",
          )}
        />
      )}
      <span className="relative z-10">{children}</span>
      {active && ctx.variant === "underline" && (
        <motion.span
          layoutId={`${ctx.layoutId}-indicator`}
          data-tab-indicator="underline"
          transition={transition}
          className="absolute -bottom-px left-0 right-0 z-10 h-[2px] rounded-full bg-ink"
        />
      )}
    </button>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `bun test tests/tabs.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/components/ui/Tabs.tsx apps/desktop/tests/tabs.test.tsx
git commit -m "feat(desktop): dual-variant sliding-indicator Tabs primitive"
```

---

### Task 8: Migrate AutomationsModal (underline)

**Files:**
- Modify: `src/components/AutomationsModal.tsx`

- [ ] **Step 1: Add the import**

Add near the other component imports:

```ts
import { Tab, Tabs } from "./ui/Tabs";
```

- [ ] **Step 2: Replace the nav**

Replace the existing `<nav>...</nav>` block (the four `<TabButton .../>` rows) with:

```tsx
        <Tabs
          value={tab}
          onChange={(v) => setTab(v as Tab)}
          variant="underline"
          className="items-center gap-5 px-6"
        >
          <TabItem value="active" label="Active" count={activeCount} active={tab === "active"} />
          <TabItem value="channels" label="Channels" count={channelCount} active={tab === "channels"} />
          <TabItem value="system" label="System" count={systemCount} active={tab === "system"} />
          <TabItem value="templates" label="Templates" active={tab === "templates"} />
        </Tabs>
```

- [ ] **Step 3: Replace the local `TabButton` with a `TabItem` wrapper**

Delete the existing `function TabButton({...}) { ... }` (the one rendering the static underline span) and replace it with:

```tsx
function TabItem({
  value,
  label,
  count,
  active,
}: {
  value: string;
  label: string;
  count?: number;
  active: boolean;
}) {
  return (
    <Tab
      value={value}
      className="inline-flex h-9 items-center gap-1.5 text-base font-medium tracking-[-0.005em] text-muted transition-colors hover:text-ink data-[active=true]:text-ink"
    >
      {label}
      {count != null && count > 0 && (
        <span
          className={clsx(
            "inline-flex h-[18px] min-w-[20px] items-center justify-center rounded-full px-1.5 text-2xs font-medium tabular-nums",
            active ? "bg-ink text-on-ink" : "bg-surface-soft text-muted",
          )}
        >
          {count}
        </span>
      )}
    </Tab>
  );
}
```

> The active text color now comes from the `data-[active=true]:text-ink` Tailwind variant (Tab sets `data-active="true"`). The badge keeps its existing `active`-driven colors via the prop. The sliding underline is supplied by the `<Tab>` indicator — the old static `<span className="absolute ... h-[2px] bg-ink">` is gone with `TabButton`.

- [ ] **Step 4: Typecheck**

Run: `cd apps/desktop && bun run tsc --noEmit`
Expected: no new type errors. (`clsx` is already imported in this file.)

- [ ] **Step 5: Manual verification**

Open the Automations modal; the underline should slide between Active/Channels/System/Templates, and badges/counts should look unchanged.

- [ ] **Step 6: Commit**

```bash
git add apps/desktop/src/components/AutomationsModal.tsx
git commit -m "refactor(desktop): AutomationsModal tabs use the shared Tabs primitive"
```

---

### Task 9: Migrate MemoryItemsPane (pill)

**Files:**
- Modify: `src/components/memory/MemoryItemsPane.tsx`

- [ ] **Step 1: Add the import**

Add near the other imports:

```ts
import { Tab, Tabs } from "../ui/Tabs";
```

- [ ] **Step 2: Replace the nav**

Replace the existing `<nav>...</nav>` block (the `TABS.map(...)` of buttons) with:

```tsx
      <Tabs
        value={tab}
        onChange={(v) => setTab(v as Tab)}
        variant="pill"
        className="flex-wrap items-center gap-1 border-b border-line-soft px-3 pb-2"
      >
        {TABS.map((entry) => (
          <Tab
            key={entry.id}
            value={entry.id}
            className="rounded-lg px-3 py-2 text-left text-muted transition-colors hover:text-ink data-[active=true]:text-ink"
          >
            <div className="text-sm font-semibold tracking-[-0.01em]">{entry.label}</div>
            <div className="text-2xs text-faint">{entry.hint}</div>
          </Tab>
        ))}
      </Tabs>
```

> The `<nav aria-label="Memory sections">` becomes `<Tabs>` (it already renders `role="tablist"`). The active pill background (previously `bg-surface-soft ... shadow-[inset_0_0_0_1px_var(--color-line-soft)]` baked into each button) is now the sliding indicator — that is the `pill` variant's default indicator class, so no `indicatorClassName` is needed. Active text color moves to the `data-[active=true]:text-ink` variant.

- [ ] **Step 3: Typecheck**

Run: `cd apps/desktop && bun run tsc --noEmit`
Expected: no new type errors.

- [ ] **Step 4: Manual verification**

Open Memory; the filled pill should slide between Today/Graph/Directories/Skills/Search, labels+hints intact, and it should still wrap correctly at narrow widths.

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/components/memory/MemoryItemsPane.tsx
git commit -m "refactor(desktop): MemoryItemsPane tabs use the shared Tabs primitive"
```

---

### Task 10: Migrate SettingsModal sidebar (vertical pill)

**Files:**
- Modify: `src/components/SettingsModal.tsx`

- [ ] **Step 1: Add the import**

Add near the other imports:

```ts
import { Tab, Tabs } from "./ui/Tabs";
```

- [ ] **Step 2: Replace the sidebar nav**

Replace the existing `<nav>...</nav>` block (the `TABS.map(...)` of `app-row` buttons) with:

```tsx
          <Tabs
            value={active}
            onChange={(v) => setActive(v as TabId)}
            variant="pill"
            orientation="vertical"
            indicatorClassName="bg-[color-mix(in_oklab,var(--color-ink)_4%,transparent)] shadow-[inset_0_0_0_1px_color-mix(in_oklab,var(--color-ink)_10%,transparent)]"
            className="gap-px px-2.5 pt-2 pb-3 overflow-y-auto scroll-thin scroll-fade-bottom"
          >
            {TABS.map((tab) => {
              const Icon = tab.icon;
              return (
                <Tab
                  key={tab.id}
                  value={tab.id}
                  className="grid w-full grid-cols-[16px_minmax(0,1fr)] items-center gap-2 px-2 py-1 rounded-lg text-base font-medium text-left tracking-[-0.005em] text-ink-soft transition-colors hover:text-ink data-[active=true]:text-ink"
                >
                  <span className="grid h-4 w-4 shrink-0 place-items-center">
                    <Icon size={ICON.LG} strokeWidth={2} />
                  </span>
                  <span className="truncate">{tab.label}</span>
                </Tab>
              );
            })}
          </Tabs>
```

> The `app-row` class + `data-active` static background is replaced by the `pill` indicator, whose `indicatorClassName` reproduces the exact `.app-row[data-active="true"]` look (ink-4% fill + ink-10% inset ring) so the visual is unchanged but now slides. The `title={tab.label}` tooltip is dropped (the label is visible); re-add it on the `<Tab>` if desired. The outer `<nav>` wrapper is replaced by `<Tabs>` (the `drag-spacer` div above it stays).

- [ ] **Step 3: Typecheck**

Run: `cd apps/desktop && bun run tsc --noEmit`
Expected: no new type errors.

- [ ] **Step 4: Manual verification**

Open Settings; the active-tab background should slide vertically between sidebar items, icons+labels intact, light and dark themes both looking right.

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/components/SettingsModal.tsx
git commit -m "refactor(desktop): SettingsModal sidebar uses the shared Tabs primitive"
```

---

## Final verification

- [ ] Run the full desktop test suite: `cd apps/desktop && bun test`
  Expected: all tests pass, including the three new files.
- [ ] Typecheck once more: `cd apps/desktop && bun run tsc --noEmit`
- [ ] Manual smoke: tabs slide on all three surfaces; a background/scheduled task completing out of view raises a clickable top-right toast that auto-dismisses; no toast when the source is already in view.

---

## Self-Review (completed during planning)

**Spec coverage:**
- Tabs dual-variant primitive (underline + pill, h/v) → Task 7; migrations → Tasks 8–10 (one per surface, matching the spec's variant table). ✓
- Toast triggers: background agents → Tasks 1/4; scheduled automations → Tasks 1/5. ✓
- Top-right anchor, click-to-jump, suppress-if-in-view, ~5s uniform auto-dismiss, unbounded stack → Task 3 (`Toaster`) + suppression in Task 1 helpers. ✓
- "No backend/transport changes" → confirmed; only client files touched. ✓
- Tokens reused (`SPRING_LAYOUT`, `MOTION.panel`, `EASE_DECELERATE`) — no inline literals. ✓
- Reduced motion honored (Tabs `useReducedMotion`; app-wide `MotionConfig`). ✓
- Out-of-scope items (error toasts, notifier mirror, action feedback, stacking cap, failure-persistence) → not implemented. ✓

**Placeholder scan:** No TBD/TODO; every code step contains full code. ✓

**Type consistency:** `Toast`/`ToastTarget`/`ToastStatus` defined once in `lib/taskToast.ts` and imported everywhere. `pushToast(toast: Toast)` / `dismissToast(id: string)` signatures match across store types, store impl, hook, view, and automation wiring. `backgroundAgentToast` id (`bg:<sid>:<tid>`) matches the watcher's `seen` key. `BackgroundAgent` fields (`taskId`/`sessionId`/`command`/`status`/`detail`) match `store/background-agent-domain.ts`. ✓
