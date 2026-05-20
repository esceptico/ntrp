# Glass Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build reusable frosted glass material primitives and wire the existing segmented control to them.

**Architecture:** CSS owns the material recipe through shared glass variables and classes. React helpers only map props to class names and data attributes, so components cannot fork the visual recipe.

**Tech Stack:** React, TypeScript, Tailwind CSS v4 global stylesheet, existing desktop Vite/Electron app.

---

### Task 1: CSS Glass Material Primitives

**Files:**
- Modify: `apps/desktop/src/styles.css`

- [x] **Step 1: Add global glass tokens and classes**

Add a glass framework section near the existing `.glass-pane` section:

```css
.glass-surface {
  --glass-tint: rgba(255, 255, 255, 0.35);
  --glass-blur: 20px;
  --glass-saturate: 180%;
  --glass-border: rgba(255, 255, 255, 0.55);
  --glass-rim: rgba(255, 255, 255, 0.6);
  --glass-shadow: rgba(31, 38, 135, 0.25);
  --glass-radius: 16px;
  background: var(--glass-tint);
  backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
  border: 1px solid var(--glass-border);
  border-radius: var(--glass-radius);
  box-shadow:
    inset 0 1px 0 var(--glass-rim),
    0 8px 24px -12px var(--glass-shadow);
}
```

- [x] **Step 2: Add variants and tones**

Add `.glass-clear`, `.glass-frosted`, `.glass-heavy`, `.glass-static`, radius classes, and `[data-tone]` overrides matching the spec.

- [x] **Step 3: Replace old pane recipes**

Replace `.glass-pane`, `.glass-pane-thick`, and `.glass-pane-static` usage with `glass-surface` plus the appropriate `glass-*` variant.

- [x] **Step 4: Verify style syntax**

Run: `cd apps/desktop && bun run typecheck`

Expected: no new CSS-related TypeScript errors.

### Task 2: React GlassSurface Helper

**Files:**
- Create: `apps/desktop/src/components/GlassSurface.tsx`

- [x] **Step 1: Add component**

Create a thin wrapper:

```tsx
import { ComponentPropsWithoutRef, forwardRef } from "react";

type GlassVariant = "clear" | "frosted" | "heavy" | "static";
type GlassTone = "auto" | "light" | "dark";
type GlassRadius = "sm" | "md" | "lg" | "pill";

interface GlassSurfaceProps extends ComponentPropsWithoutRef<"div"> {
  variant?: GlassVariant;
  tone?: GlassTone;
  radius?: GlassRadius;
}
```

It should render a `div` with `glass-surface glass-${variant} glass-radius-${radius}`, omit `data-tone` for `auto`, and merge `className`.

- [x] **Step 2: Type-check**

Run: `cd apps/desktop && bun run typecheck`

Expected: component compiles.

### Task 3: Refactor GlassToggle Onto Framework

**Files:**
- Modify: `apps/desktop/src/components/GlassToggle.tsx`

- [x] **Step 1: Remove duplicated material recipe**

Delete `TONES.track`, `TONES.rim`, `TONES.trackBorder`, and inline track backdrop styles.

- [x] **Step 2: Use framework classes**

The root track should use:

```tsx
className={`glass-surface ${blur ? "glass-frosted" : "glass-clear"} glass-radius-pill glass-toggle`}
data-tone={tone === "auto" ? undefined : tone}
```

- [x] **Step 3: Keep motion behavior**

Preserve ref measurement and `transform: translateX(...)` plus `width`.

- [x] **Step 4: Keep active pill cheap**

Use a static pill style with rgba tint, inset top highlight, and shadow. Do not add live backdrop blur to the pill.

- [x] **Step 5: Type-check**

Run: `cd apps/desktop && bun run typecheck`

Expected: no type errors from `GlassToggle`.

### Task 4: Verification

**Files:**
- Inspect: `apps/desktop/src/components/settings/ToolsTab.tsx`
- Inspect: `apps/desktop/src/components/settings/MCPTab.tsx`

- [x] **Step 1: Verify no unrelated changes**

Run: `git diff -- apps/desktop/src/components/settings/ToolsTab.tsx apps/desktop/src/components/settings/MCPTab.tsx`

Expected: existing user edits only; do not alter settings behavior.

- [x] **Step 2: Run focused checks**

Run: `cd apps/desktop && bun run typecheck`

Expected: pass or only pre-existing unrelated failures.

- [x] **Step 3: Review diff**

Run: `git diff -- apps/desktop/src/styles.css apps/desktop/src/components/GlassSurface.tsx apps/desktop/src/components/GlassToggle.tsx`

Expected: only glass framework and toggle material refactor.
