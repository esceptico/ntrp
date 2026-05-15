# Desktop Optimization Sweep — Design

**Date:** 2026-05-15
**Scope:** `apps/desktop/`
**Reference:** [motion.dev tier list](https://motion.dev/magazine/web-animation-performance-tier-list)

## Goal

Reduce render cost on hot paths and lower cognitive load by splitting the largest files into focused units. Keep visual + behavioral parity unless flagged.

## Phase C — Shared modal-shell dedup (SHIPPED this session)

Added `header?: { title; subtitle?; actions? }` slot to `PageModal`. When provided, PageModal renders the standard header bar with title, optional subtitle, any extra action buttons, and an always-included close X.

**Migrated:** MarkdownViewer, ArchiveModal, AutomationsModal.

**Intentionally not migrated:**
- SettingsModal — has a sidebar+content layout; the per-tab title lives inside the content pane, not at the modal top.
- MemoryModal — tab strip sits where the header would.
- ApprovalReviewModal — different visual style (smaller, lives near approval flow). Also still uses the spatial-origin animation that was removed from PageModal last session — that's a separate consistency fix.
- ToolViewer — uses `bg-surface` instead of `.glass-pane-thick`; migrating would change material. Park as a future visual-alignment task.

## Phase B — Component decomposition (NEXT SESSION, one target)

**Recommended target:** `Composer.tsx` (769 lines). Highest-touch file in the app.

Split into a `components/composer/` folder:

```
composer/
  Composer.tsx              ~150  orchestrator: state, refs, top-level layout
  ComposerInput.tsx         ~200  textarea, autosize, key handling, draft binding
  ComposerStateOverlay.tsx  ~150  thinking rim, send pulse, tool shine, leaving states
  ComposerToolbar.tsx       ~200  model picker trigger, command picker trigger, send button, command picker portal
```

### Split criteria

- `Composer.tsx` owns: hooks that need full-component scope (running state, focus, scroll integration, the data-attributes that drive CSS), composition of subcomponents.
- `ComposerInput.tsx` owns: textarea ref + autosize logic + keyboard handlers (Enter, Shift-Enter, Cmd-K, arrow-up for prior message). Pure controlled component, props in/out.
- `ComposerStateOverlay.tsx` owns: the `data-thinking`, `data-just-sent`, `data-thinking-leaving` overlay markup. Receives running/sent/leaving booleans. No internal state beyond animation timing.
- `ComposerToolbar.tsx` owns: model picker button + portal, command picker button + portal, send button. Slot for ComposerInput between them or above them per current layout.

### Migration ordering

1. Create `composer/` folder, copy `Composer.tsx` in as `Composer.tsx` (the orchestrator).
2. Extract `ComposerInput` first (most self-contained).
3. Extract `ComposerStateOverlay` next (purely presentational).
4. Extract `ComposerToolbar` last (touches model + command pickers, which have their own portals).
5. Update import in `Chat.tsx` (single line).
6. Delete the old `Composer.tsx` (renamed to folder).

### Risks

- Composer has intricate state coupling (thinking → leaving → done; just-sent overlapping with new-stream-start). Subcomponents must accept those flags as props rather than re-deriving from store, or they'll desync.
- The command picker portal escapes the composer's backdrop-filter parent (bug burned us 3x per memory). Must remain a portal sibling after the split.

### Out of scope for B

- CommandPalette (710), Sidebar (706), MCPTab (771) — each is its own future session.

## Phase A — Store + actions slices (LATER SESSION)

Split `store.ts` (984 lines) into per-feature slices using Zustand's slices pattern:

```
store/
  index.ts              create<RootState>()(...slices, persist config)
  types.ts              RootState = SessionSlice & MessagesSlice & ...
  slices/
    session.ts          currentSessionId, sessions list, switching, archiving
    messages.ts         order, byId map, history paging, source focus
    prefs.ts            sidebarWidth, theme, palette, sidebarHidden, reasoning toggle, etc.
    approvals.ts        pendingApprovals, reviewingApprovalToolId, modalOrigin
    memory.ts           viewingMarkdown, memory tabs state
    automations.ts      automations list, automation modals state
    runs.ts             activeRuns, streaming markers
    ui.ts               settingsOpen, automationsOpen, archiveOpen, memoryOpen, command palette
```

`actions.ts` (933 lines) follows the same per-feature split into `actions/{session,messages,prefs,...}.ts`.

### Public API invariant

`useStore` selector signatures stay identical. Every existing call site:

```ts
useStore((s) => s.currentSessionId)
useStore((s) => s.openSettings)
useStore.getState().prefs.sidebarWidth
```

continues to work. Slice typing merges via intersection — TypeScript resolves the flat shape from the union.

### Migration ordering

1. Create `store/index.ts` + `store/types.ts` + empty slice files.
2. Move state + actions one slice at a time. After each slice, run typecheck — no call site edits should be required.
3. Once all slices migrated, delete old `store.ts` and update barrel import.
4. Apply same pattern to `actions.ts` → `actions/`.

### Risks

- Persist config currently lives in `store.ts` and targets specific keys in `prefs`. Must stay pointing at the same keys (localStorage shape stays).
- Some actions read multiple slices (e.g. `createSession` writes to session, messages, and runs). Cross-slice access via `get()` works but is slightly less ergonomic — fine, no API change needed.

### Validation

- Typecheck after every slice extraction.
- Open the app, check: session switching, sidebar resize (already perf-fixed), approval flow, settings open/close, memory pane, theme toggle. If all work without code edits at call sites, the public API stayed intact.

## Non-goals

- No new features.
- No styling changes beyond what's required for migrations (e.g. PageModal header consolidating prior per-modal padding to one canonical value).
- No splitting api.ts (1304) — that's data, not coupling. Splitting it doesn't reduce cognitive load proportionally.
- No splitting useEvents.ts (655) — single hook, single concern; size reflects necessary complexity of SSE event handling.

## Order to ship

1. Phase B (one session). Composer split.
2. Phase A (one session). Store + actions slices.

Each is its own PR, reviewable end-to-end.
