import { expect, test } from "bun:test";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { JSDOM } from "jsdom";
import { ScrollBlurTop } from "../src/components/ScrollBlur.tsx";

test("top blur observes the message scroller without living inside its scroll flow", async () => {
  const dom = new JSDOM('<!doctype html><div id="root"></div>', { url: "http://localhost" });
  const testGlobal = globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean };
  const prev = {
    window: globalThis.window,
    document: globalThis.document,
    act: testGlobal.IS_REACT_ACT_ENVIRONMENT,
  };
  testGlobal.IS_REACT_ACT_ENVIRONMENT = true;
  globalThis.window = dom.window as unknown as Window & typeof globalThis;
  globalThis.document = dom.window.document;

  try {
    const rootEl = dom.window.document.getElementById("root");
    if (!rootEl) throw new Error("missing root");

    const scroller = dom.window.document.createElement("div");
    const blurHost = dom.window.document.createElement("div");
    rootEl.append(scroller, blurHost);

    const root = createRoot(blurHost);
    await act(async () => {
      root.render(<ScrollBlurTop scrollerRef={{ current: scroller }} />);
    });

    const blur = blurHost.querySelector<HTMLElement>(".scroll-progressive-blur-top");
    expect(blur).not.toBeNull();
    expect(blur?.parentElement).toBe(blurHost);
    expect(scroller.contains(blur)).toBe(false);
    expect(blur?.dataset.scrolled).toBe("false");

    await act(async () => {
      scroller.scrollTop = 12;
      scroller.dispatchEvent(new dom.window.Event("scroll"));
    });
    expect(blur?.dataset.scrolled).toBe("true");

    await act(async () => {
      scroller.scrollTop = 0;
      scroller.dispatchEvent(new dom.window.Event("scroll"));
    });
    expect(blur?.dataset.scrolled).toBe("false");

    await act(async () => root.unmount());
  } finally {
    globalThis.document = prev.document;
    globalThis.window = prev.window;
    testGlobal.IS_REACT_ACT_ENVIRONMENT = prev.act;
  }
});
