import { afterEach, expect, test } from "bun:test";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { JSDOM } from "jsdom";
import { ConnectionStatus } from "../src/components/ConnectionStatus.tsx";
import { setState } from "../src/store/index.ts";
import type { ConnectionPhase } from "../src/store/domains.ts";

const originalWindow = globalThis.window;
const originalDocument = globalThis.document;
type ActFlag = typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean };
const originalAct = (globalThis as ActFlag).IS_REACT_ACT_ENVIRONMENT;

afterEach(() => {
  globalThis.window = originalWindow;
  globalThis.document = originalDocument;
  (globalThis as ActFlag).IS_REACT_ACT_ENVIRONMENT = originalAct;
});

async function renderPhase(phase: ConnectionPhase): Promise<string> {
  const dom = new JSDOM('<!doctype html><div id="root"></div>', { url: "http://localhost" });
  globalThis.window = dom.window as unknown as Window & typeof globalThis;
  globalThis.document = dom.window.document;
  (globalThis as ActFlag).IS_REACT_ACT_ENVIRONMENT = true;
  const rootEl = dom.window.document.getElementById("root");
  if (!rootEl) throw new Error("missing root");
  const root = createRoot(rootEl);
  setState({ connectionPhase: phase });
  await act(async () => {
    root.render(<ConnectionStatus />);
  });
  await act(async () => {
    await Promise.resolve();
  });
  const text = rootEl.textContent ?? "";
  await act(async () => {
    root.unmount();
  });
  return text;
}

test("ConnectionStatus stays hidden while healthy or first-connecting", async () => {
  for (const phase of ["idle", "connecting", "connected"] as ConnectionPhase[]) {
    const text = await renderPhase(phase);
    expect(text).not.toContain("Reconnecting");
    expect(text).not.toContain("Offline");
  }
});

test("ConnectionStatus surfaces a pill for degraded phases", async () => {
  expect(await renderPhase("reconnecting")).toContain("Reconnecting");
  expect(await renderPhase("disconnected")).toContain("Offline");
  expect(await renderPhase("failed")).toContain("Offline");
});
