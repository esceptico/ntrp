# Quick-capture fix (2026-06-13)

User report: pressing the shortcut makes the app disappear from the Dock; behavior weird; UX/UI bad.

Root causes found (apps/desktop, Electron):
- **Dock icon vanishing**: `setVisibleOnAllWorkspaces(true, {visibleOnFullScreen: true})` transforms the
  process type to UIElementApplication → Dock icon removed. Fix: `skipTransformProcessType: true`.
- `dismissQuickWindow()` called `app.hide()` → hid ALL ntrp windows (main window vanished on Esc/blur)
- `quick:submit` force-showed + focused the main window → yanked user out of their current app
- UI: shadow clipped by 6px window padding, no animation, positioned at 78% height near the dock

## Done
- [x] Quick window → non-activating macOS panel (`type: "panel"`): keyboard focus without app activation
- [x] `skipTransformProcessType: true` → Dock icon stays (verified on screen)
- [x] Deleted `app.hide()` + `quickSummonedFromForeground` machinery (verified: main window survives dismiss)
- [x] Silent capture: submit no longer raises the main window; creates it hidden if closed
- [x] `activate` handler counts only the main window (dock click works after closing it)
- [x] Eager panel creation at startup + `isLoading` guard (first-summon race)
- [x] Renderer focus-retry loop per summon (panel page focus is racy; single .select() drops keystrokes)
- [x] Esc: AppKit eats it at the NSPanel layer (verified: before-input-event sees every key EXCEPT Escape) →
      registered as a global shortcut only while the panel is visible, released on dismiss
- [x] Electron 39 → 42.4.0 (user request; breaking changes 40–42 don't touch our APIs)
- [x] UI: Spotlight position (top third), shadow breathing room (668×100 window, padded card),
      entry spring + dissolve exit (house poses), draft preserved on blur (pre-selected on resummon)
- [x] Typecheck clean, 421 tests pass; live-verified: summon over Finder, type, Esc, Enter-submit

## Round 2 (same day)
- [x] #1 Quick captures no longer inherit the current session's project — `createSession(null)` → Inbox
- [x] #2 Screen capture: camera button → `screencapture -i -x` interactive snip (panel hides during
      selection, re-presents with draft intact); chips in the card, up to 3, click to remove;
      images flow through quick:submit payload → sendMessage(text, images)
- [x] #3 Position lowered to 64% of work area (was top-third)
- [x] #4 Chat selector: "New chat ⌄" chip → recent-chats picker (window grows via quick:resize,
      top edge fixed); ArrowDown opens/navigates, Enter picks, Esc closes picker first, then panel;
      submit routes via switchSession(sessionId) in the main renderer
- [x] Typecheck + 421 tests pass; renderer UI verified in browser preview (card + picker, no console errors)
- NOT live-verified in Electron (user asked to stop computer-use): snip flow, window resize, Esc layering
- Requires dev app restart (main.cjs changed); first snip will trigger macOS Screen Recording permission

## Round 3 — "asks for API key every launch" after Electron 42 bump (RESOLVED, user-confirmed)
- Root cause: Electron 42 changed `safeStorage.decryptStringAsync` to resolve `{shouldReEncrypt, result}`
  instead of the string → object fell into normalizeConfig → apiKey coerced to "" → key dialog every launch.
- Also found on 42.4.0/macOS: async↔sync key stores incompatible; `encryptStringAsync` sporadic SIGSEGV.
- Fix: encryptSecret/decryptSecret are sync-only (`encryptString`/`decryptString`); verified cross-process
  round-trip via Keychain. Keychain kept in dev (user rejected plaintext-dev workaround — rightly).
- Dead ends to not repeat: Keychain ACL/ad-hoc-signing theory, duplicate-item roulette theory,
  keychain item deletions. See lessons.md ("Print the VALUE, not just the error").

## Notes
- Submit pipeline (quick:message → main renderer createSession+sendMessage) is unchanged from before;
  visually confirmed the main window switched to a fresh session after submit, response content not
  inspected (server API needs auth header).
- NOT committed — awaiting user review. Dev app left running.
