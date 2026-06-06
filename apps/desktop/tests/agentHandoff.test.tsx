import { afterEach, expect, test } from "bun:test";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { JSDOM } from "jsdom";
import { AgentRunRow } from "../src/components/agents/AgentRunCard.tsx";
import type { AgentRunStatus, AgentRunView } from "../src/lib/agentRun.ts";

const originalWindow = globalThis.window;
const originalDocument = globalThis.document;
type ActFlag = typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean };
const originalAct = (globalThis as ActFlag).IS_REACT_ACT_ENVIRONMENT;

afterEach(() => {
  globalThis.window = originalWindow;
  globalThis.document = originalDocument;
  (globalThis as ActFlag).IS_REACT_ACT_ENVIRONMENT = originalAct;
});

function runWith(status: AgentRunStatus): AgentRunView {
  return { key: "k1", name: "Research auth flow", type: "Research", status, elapsedLabel: "" };
}

async function renderRow(status: AgentRunStatus) {
  const dom = new JSDOM('<!doctype html><div id="root"></div>', { url: "http://localhost" });
  globalThis.window = dom.window as unknown as Window & typeof globalThis;
  globalThis.document = dom.window.document;
  (globalThis as ActFlag).IS_REACT_ACT_ENVIRONMENT = true;
  const rootEl = dom.window.document.getElementById("root");
  if (!rootEl) throw new Error("missing root");
  const root = createRoot(rootEl);
  await act(async () => {
    root.render(
      <AgentRunRow run={runWith(status)} handoff={{ onReply: () => {}, onRoute: () => {} }} />,
    );
  });
  const has = (label: string) => !!dom.window.document.querySelector(`[aria-label="${label}"]`);
  const result = { reply: has("Reply with result"), route: has("Route to a new agent") };
  await act(async () => {
    root.unmount();
  });
  return result;
}

test("finished agents expose reply + route handoff actions", async () => {
  const r = await renderRow("completed");
  expect(r.reply).toBe(true);
  expect(r.route).toBe(true);
});

test("running agents do not show handoff actions", async () => {
  const r = await renderRow("running");
  expect(r.reply).toBe(false);
  expect(r.route).toBe(false);
});
