import { expect, test } from "bun:test";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { JSDOM } from "jsdom";
import { SuggestionCard, SuggestionsSection } from "@/features/automations/components/AutomationsModal";
import type { AutomationSuggestion } from "@/api/types";

function suggestion(overrides: Partial<AutomationSuggestion> = {}): AutomationSuggestion {
  return {
    id: "s1",
    name: "Weekly ntrp PR digest",
    description: "Summarize merged PRs in ntrp this week.",
    triggers: [{ type: "time", at: "09:00", days: "mon" }],
    rationale: "You review ntrp PRs most mornings",
    evidence: ["recent PR reviews"],
    category: "Status reports",
    icon: "GitPullRequest",
    ...overrides,
  };
}

// ─── Static render ───────────────────────────────────────────────────

test("an empty suggestion list renders nothing (cold-start hides the section)", () => {
  expect(renderToStaticMarkup(<SuggestionsSection suggestions={[]} onPick={() => {}} />)).toBe("");
  expect(renderToStaticMarkup(<SuggestionsSection suggestions={null} onPick={() => {}} />)).toBe("");
});

test("the section renders the heading and a card per suggestion", () => {
  const html = renderToStaticMarkup(
    <SuggestionsSection
      suggestions={[suggestion(), suggestion({ id: "s2", name: "Inbox triage" })]}
      onPick={() => {}}
    />,
  );
  expect(html).toContain("Suggested for you");
  expect(html).toContain("Weekly ntrp PR digest");
  expect(html).toContain("Inbox triage");
});

test("a card shows the rationale as its blurb and a schedule chip", () => {
  const html = renderToStaticMarkup(<SuggestionCard suggestion={suggestion()} onPick={() => {}} />);
  expect(html).toContain("You review ntrp PRs most mornings");
  // Schedule chip derived from the trigger formatter.
  expect(html).toContain("at 09:00 · mon");
  // The card does not surface the raw prompt/description.
  expect(html).not.toContain("Summarize merged PRs in ntrp this week.");
});

test("an event-trigger card formats the event schedule chip", () => {
  const html = renderToStaticMarkup(
    <SuggestionCard
      suggestion={suggestion({ triggers: [{ type: "event", event_type: "approaching", lead_minutes: 15 }] })}
      onPick={() => {}}
    />,
  );
  expect(html).toContain("on:approaching (15m)");
});

// ─── Interaction (JSDOM) ─────────────────────────────────────────────

test("clicking a card seeds the editor with the mapped payload", async () => {
  const { dom, rootEl, root, restore } = setupDom();
  try {
    let picked: AutomationSuggestion | null = null;
    await act(async () => {
      root.render(<SuggestionCard suggestion={suggestion()} onPick={(s) => (picked = s)} />);
    });

    // The card's open action is the stretched accessible overlay <button>.
    const trigger = rootEl.querySelector('[data-suggestion="s1"] button[aria-label^="Use suggestion"]');
    if (!trigger) throw new Error("missing suggestion open button");
    await act(async () => {
      trigger.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
    });

    expect(picked).not.toBeNull();
    expect((picked as AutomationSuggestion).id).toBe("s1");

    await act(async () => root.unmount());
  } finally {
    restore();
  }
});

test("the dismiss button fires onDismiss without triggering the card click", async () => {
  const { dom, rootEl, root, restore } = setupDom();
  try {
    let picked = 0;
    let dismissed: string | null = null;
    await act(async () => {
      root.render(
        <SuggestionCard
          suggestion={suggestion()}
          onPick={() => (picked += 1)}
          onDismiss={(id) => (dismissed = id)}
        />,
      );
    });

    const dismissButton = [...rootEl.querySelectorAll("button")].find(
      (b) => b.getAttribute("aria-label") === "Dismiss suggestion",
    );
    if (!dismissButton) throw new Error("missing dismiss button");
    await act(async () => {
      dismissButton.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
    });

    expect(dismissed).toBe("s1");
    expect(picked).toBe(0);

    await act(async () => root.unmount());
  } finally {
    restore();
  }
});

// ─── helpers ─────────────────────────────────────────────────────────

function setupDom() {
  const dom = new JSDOM('<!doctype html><div id="root"></div>', { url: "http://localhost" });
  const testGlobal = globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean };
  const prev = {
    window: globalThis.window,
    document: globalThis.document,
    act: testGlobal.IS_REACT_ACT_ENVIRONMENT,
    resizeObserver: globalThis.ResizeObserver,
    raf: globalThis.requestAnimationFrame,
    caf: globalThis.cancelAnimationFrame,
  };
  testGlobal.IS_REACT_ACT_ENVIRONMENT = true;
  globalThis.window = dom.window as unknown as Window & typeof globalThis;
  globalThis.document = dom.window.document;
  // jsdom/bun lack these; ShowMore (overflow measure) + motion need them.
  globalThis.ResizeObserver =
    dom.window.ResizeObserver ??
    (class {
      observe() {}
      unobserve() {}
      disconnect() {}
    } as unknown as typeof ResizeObserver);
  globalThis.requestAnimationFrame = ((cb: FrameRequestCallback) =>
    setTimeout(() => cb(Date.now()), 0) as unknown as number) as typeof requestAnimationFrame;
  globalThis.cancelAnimationFrame = ((handle: number) =>
    clearTimeout(handle as unknown as ReturnType<typeof setTimeout>)) as typeof cancelAnimationFrame;

  const rootEl = dom.window.document.getElementById("root");
  if (!rootEl) throw new Error("missing root");
  const root = createRoot(rootEl);

  const restore = () => {
    globalThis.document = prev.document;
    globalThis.window = prev.window;
    testGlobal.IS_REACT_ACT_ENVIRONMENT = prev.act;
    globalThis.ResizeObserver = prev.resizeObserver;
    globalThis.requestAnimationFrame = prev.raf;
    globalThis.cancelAnimationFrame = prev.caf;
  };
  return { dom, rootEl, root, restore };
}
