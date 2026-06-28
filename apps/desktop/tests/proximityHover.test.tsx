import { afterEach, expect, test } from "bun:test";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { JSDOM } from "jsdom";
import { AnchoredPopover } from "@/components/ui/AnchoredPopover";
import { MenuItem } from "@/components/ui/MenuItem";

const originalWindow = globalThis.window;
const originalDocument = globalThis.document;
type ActFlag = typeof globalThis & {
  IS_REACT_ACT_ENVIRONMENT?: boolean;
  requestAnimationFrame?: typeof requestAnimationFrame;
  cancelAnimationFrame?: typeof cancelAnimationFrame;
};
const originalAct = (globalThis as ActFlag).IS_REACT_ACT_ENVIRONMENT;
const originalDOMRect = (globalThis as unknown as { DOMRect?: unknown }).DOMRect;

afterEach(() => {
  globalThis.window = originalWindow;
  globalThis.document = originalDocument;
  (globalThis as ActFlag).IS_REACT_ACT_ENVIRONMENT = originalAct;
  (globalThis as unknown as { DOMRect?: unknown }).DOMRect = originalDOMRect;
});

function setupDom(): { appEl: HTMLElement; root: Root; restore: () => void } {
  const dom = new JSDOM('<!doctype html><div id="root"></div><div id="app"></div>', {
    url: "http://localhost",
  });
  globalThis.window = dom.window as unknown as Window & typeof globalThis;
  globalThis.document = dom.window.document;
  // AnchoredPopover does `anchor instanceof DOMRect`; expose jsdom's DOMRect.
  (globalThis as unknown as { DOMRect: unknown }).DOMRect = dom.window.DOMRect;
  const g = globalThis as ActFlag;
  g.IS_REACT_ACT_ENVIRONMENT = true;
  // jsdom has no rAF; the proximity hook schedules its measure on rAF, so give
  // it a synchronous shim (also exercises the cancel path on unmount).
  if (typeof g.requestAnimationFrame !== "function") {
    g.requestAnimationFrame = ((cb: FrameRequestCallback) =>
      setTimeout(() => cb(0), 0) as unknown as number) as typeof requestAnimationFrame;
    g.cancelAnimationFrame = ((id: number) => clearTimeout(id)) as typeof cancelAnimationFrame;
  }

  const rootEl = dom.window.document.getElementById("root");
  const appEl = dom.window.document.getElementById("app");
  if (!rootEl || !appEl) throw new Error("missing root");
  return {
    appEl,
    root: createRoot(rootEl),
    restore: () => {
      globalThis.window = originalWindow;
      globalThis.document = originalDocument;
      (globalThis as ActFlag).IS_REACT_ACT_ENVIRONMENT = originalAct;
    },
  };
}

const rows = (
  <>
    <MenuItem onClick={() => {}}>One</MenuItem>
    <MenuItem onClick={() => {}}>Two</MenuItem>
    <MenuItem onClick={() => {}}>Three</MenuItem>
  </>
);

// proximity off (default) — existing consumers must be untouched: rows keep
// their own hover background and carry no proximity marker; no highlight node.
test("AnchoredPopover without proximity leaves MenuItem hover background intact", async () => {
  const { appEl, root, restore } = setupDom();
  await act(async () => {
    root.render(
      <AnchoredPopover open onClose={() => {}} anchor={{ x: 10, y: 10 }} ariaLabel="Test">
        {rows}
      </AnchoredPopover>,
    );
  });

  const buttons = appEl.querySelectorAll("button");
  expect(buttons.length).toBe(3);
  // Per-row hover background still present (today's behavior).
  expect(buttons[0].className).toContain("hover:bg-surface-soft/60");
  // No proximity wiring.
  expect(appEl.querySelectorAll("[data-proximity-item]").length).toBe(0);
  expect(appEl.querySelector("div[aria-hidden]")).toBeNull();

  await act(async () => root.unmount());
  restore();
});

// proximity on — the render must NOT loop (a fresh-object-in-effect-dep trap
// would trip React's max-update-depth here). Rows get the marker + drop their
// own hover bg (the traveling highlight owns it) while keeping text hover.
test("AnchoredPopover with proximity marks rows and suppresses MenuItem hover bg without looping", async () => {
  const { appEl, root, restore } = setupDom();
  await act(async () => {
    root.render(
      <AnchoredPopover open onClose={() => {}} anchor={{ x: 10, y: 10 }} ariaLabel="Test" proximity>
        {rows}
      </AnchoredPopover>,
    );
  });
  // Let the scheduled rAF measure flush — if the hook looped, this throws.
  await act(async () => {
    await new Promise((r) => setTimeout(r, 5));
  });

  const buttons = appEl.querySelectorAll("button");
  expect(buttons.length).toBe(3);
  // Every row opts into proximity tracking.
  expect(appEl.querySelectorAll("[data-proximity-item]").length).toBe(3);
  // Hover background suppressed (no double-paint over the highlight)…
  expect(buttons[0].className).not.toContain("hover:bg-surface-soft/60");
  expect(buttons[0].className).not.toContain("focus-visible:bg-surface-soft/60");
  // …but text hover kept, and rows stack above the absolute highlight.
  expect(buttons[0].className).toContain("hover:text-ink");
  expect(buttons[0].className).toContain("z-[1]");
  // Highlight is absent until a row is hovered (AnimatePresence empty).
  expect(appEl.querySelector("div[aria-hidden]")).toBeNull();

  await act(async () => root.unmount());
  restore();
});

// Keyboard focus drives the highlight too: focusing a tracked row (as roving
// Arrow/Home/End nav does) sets the active index and renders the traveling
// highlight — without a render loop (the focus handler writes the same
// primitive index the pointer uses; activeRect is never an effect dep).
test("AnchoredPopover with proximity moves the highlight to a keyboard-focused row", async () => {
  const { appEl, root, restore } = setupDom();
  await act(async () => {
    root.render(
      <AnchoredPopover
        open
        onClose={() => {}}
        anchor={{ x: 10, y: 10 }}
        ariaLabel="Test"
        variant="menu"
        proximity
      >
        <MenuItem role="menuitem" tabIndex={-1} onClick={() => {}}>
          One
        </MenuItem>
        <MenuItem role="menuitem" tabIndex={-1} onClick={() => {}}>
          Two
        </MenuItem>
        <MenuItem role="menuitem" tabIndex={-1} onClick={() => {}}>
          Three
        </MenuItem>
      </AnchoredPopover>,
    );
  });
  // Flush the open-time effects (positioning + initial menuitem focus) and the
  // proximity rAF measure. If the keyboard path looped, this throws.
  await act(async () => {
    await new Promise((r) => setTimeout(r, 10));
  });

  const items = appEl.querySelectorAll<HTMLElement>('[role="menuitem"]');
  expect(items.length).toBe(3);

  // Focus the second row (what ArrowDown would land on) and let state settle.
  await act(async () => {
    items[1].focus();
  });
  await act(async () => {
    await new Promise((r) => setTimeout(r, 5));
  });

  // The traveling highlight is now present (a focused row activated it).
  expect(appEl.querySelector("div[aria-hidden]")).not.toBeNull();
  // Focus stayed where roving nav put it (no focus-restore regression).
  expect(globalThis.document.activeElement).toBe(items[1]);

  await act(async () => root.unmount());
  restore();
});

// A bare MenuItem (no AnchoredPopover context) keeps default hover — the
// context defaults to false so non-proximity call sites are unaffected.
test("MenuItem outside a proximity popover keeps its hover background", async () => {
  const { root, restore } = setupDom();
  await act(async () => {
    root.render(<MenuItem onClick={() => {}}>Bare</MenuItem>);
  });
  const button = globalThis.document.getElementById("root")?.querySelector("button");
  expect(button?.className).toContain("hover:bg-surface-soft/60");
  expect(button?.hasAttribute("data-proximity-item")).toBe(false);

  await act(async () => root.unmount());
  restore();
});
