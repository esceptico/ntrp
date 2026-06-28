import { expect, test } from "bun:test";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { AgentRunRow } from "@/components/ui/AgentRunRow";
import type { AgentRunStatus, AgentRunView } from "@/lib/agentRun";

function runWith(status: AgentRunStatus): AgentRunView {
  return { key: "k1", name: "Research auth flow", type: "Research", status, elapsedLabel: "" };
}

async function renderRow(status: AgentRunStatus) {
  const rootEl = document.createElement("div");
  document.body.append(rootEl);
  const root = createRoot(rootEl);
  await act(async () => {
    root.render(
      <AgentRunRow run={runWith(status)} handoff={{ onReply: () => {}, onRoute: () => {} }} />,
    );
  });
  const has = (label: string) => !!rootEl.querySelector(`[aria-label="${label}"]`);
  const result = { reply: has("Reply with result"), route: has("Route to a new agent") };
  await act(async () => {
    root.unmount();
  });
  rootEl.remove();
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
