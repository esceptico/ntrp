import { afterEach, expect, test } from "bun:test";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { JSDOM } from "jsdom";
import { ToolViewer } from "@/components/ToolViewer";
import { setState } from "@/store/index";
import { createBackgroundAgentsDomainState } from "@/store/background-agent-domain";
import type { ActivityItem } from "@/store/types";

const originalWindow = globalThis.window;
const originalDocument = globalThis.document;
const originalAct = (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT;

afterEach(() => {
  globalThis.window = originalWindow;
  globalThis.document = originalDocument;
  (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = originalAct;
});

test("agent inspector loads durable child-agent result by child run id", async () => {
  const { appEl, root, restore } = setupDom();
  const requests: string[] = [];
  const item: ActivityItem = {
    id: "call-bg",
    kind: "background",
    semanticKind: "agent",
    target: "background",
    args: JSON.stringify({ task: "research auth flow" }),
    result: "Background task child-run-1 started: research auth flow",
    status: "executed",
    taskStatus: "completed",
    childAgent: {
      childRunId: "child-run-1",
      parentToolCallId: "call-bg",
      agentType: "background_research",
      wait: false,
      status: "completed",
    },
  };

  globalThis.window.ntrpDesktop = {
    api: {
      request: async (_config: unknown, req: { path: string }) => {
        requests.push(req.path);
        return {
          ok: true,
          status: 200,
          statusText: "OK",
          contentType: "application/json",
          data: {
            task_id: "child-run-1",
            child_run_id: "child-run-1",
            session_id: "sess-1",
            status: "completed",
            terminal: true,
            result: "final report",
            result_ref: "bg_results/child-run-1.txt",
          },
          text: "",
        };
      },
    },
  };

  setState({
    config: { serverUrl: "http://localhost:6877", apiKey: "" },
    currentSessionId: "sess-1",
    messages: new Map([
      [
        "activity-1",
        {
          id: "activity-1",
          role: "activity",
          content: "",
          activity: { items: [item], label: "Called", done: true },
        },
      ],
    ]),
    order: ["activity-1"],
    viewingTool: item,
    backgroundAgents: createBackgroundAgentsDomainState(),
  });

  try {
    await act(async () => {
      root.render(<ToolViewer />);
    });
    await act(async () => {
      await Promise.resolve();
    });

    expect(requests).toEqual([
      "/chat/child-agents/child-run-1/result?session_id=sess-1",
    ]);
    expect(appEl.textContent).toContain("final report");
  } finally {
    await act(async () => root.unmount());
    restore();
  }
});

test("agent inspector keeps waited child-agent local result without fetching durable row", async () => {
  const { appEl, root, restore } = setupDom();
  const requests: string[] = [];
  const item: ActivityItem = {
    id: "call-research",
    kind: "research",
    semanticKind: "agent",
    target: "research",
    args: JSON.stringify({ task: "research auth flow" }),
    result: "local final report",
    status: "executed",
    taskStatus: "completed",
    childAgent: {
      childRunId: "child-run-waited",
      parentToolCallId: "call-research",
      agentType: "research",
      wait: true,
      status: "completed",
    },
  };

  globalThis.window.ntrpDesktop = {
    api: {
      request: async (_config: unknown, req: { path: string }) => {
        requests.push(req.path);
        throw new Error("unexpected request");
      },
    },
  };

  setState({
    config: { serverUrl: "http://localhost:6877", apiKey: "" },
    currentSessionId: "sess-1",
    messages: new Map([
      [
        "activity-1",
        {
          id: "activity-1",
          role: "activity",
          content: "",
          activity: { items: [item], label: "Called", done: true },
        },
      ],
    ]),
    order: ["activity-1"],
    viewingTool: item,
    backgroundAgents: createBackgroundAgentsDomainState(),
  });

  try {
    await act(async () => {
      root.render(<ToolViewer />);
    });
    await act(async () => {
      await Promise.resolve();
    });

    expect(requests).toEqual([]);
    expect(appEl.textContent).toContain("local final report");
  } finally {
    await act(async () => root.unmount());
    restore();
  }
});

test("agent inspector activity tree labels nested child agents with type and mode", async () => {
  const { appEl, root, restore } = setupDom();
  const rootItem: ActivityItem = {
    id: "call-research",
    kind: "research",
    semanticKind: "agent",
    target: "research",
    args: JSON.stringify({ task: "research auth flow" }),
    result: "root report",
    status: "executed",
    taskStatus: "completed",
  };
  const nestedAgent: ActivityItem = {
    id: "call-bg",
    kind: "background",
    semanticKind: "agent",
    target: "background",
    displayName: "Nested research",
    parentToolId: "call-research",
    depth: 1,
    status: "ongoing",
    taskStatus: "running",
    childAgent: {
      childRunId: "child-run-2",
      parentToolCallId: "call-bg",
      agentType: "background_research",
      wait: false,
      status: "running",
    },
  };

  setState({
    config: { serverUrl: "http://localhost:6877", apiKey: "" },
    currentSessionId: "sess-1",
    messages: new Map([
      [
        "activity-1",
        {
          id: "activity-1",
          role: "activity",
          content: "",
          activity: { items: [rootItem, nestedAgent], label: "Called", done: true },
        },
      ],
    ]),
    order: ["activity-1"],
    viewingTool: rootItem,
    backgroundAgents: createBackgroundAgentsDomainState(),
  });

  try {
    await act(async () => {
      root.render(<ToolViewer />);
    });

    expect(appEl.textContent).toContain("Nested research");
    // De-id'd: humanized type + mode, no raw run id leaked into the label.
    expect(appEl.textContent).toContain("Research · detached");
    expect(appEl.textContent).not.toContain("child-run-2");
  } finally {
    await act(async () => root.unmount());
    restore();
  }
});

function setupDom(): { appEl: HTMLElement; root: Root; restore: () => void } {
  const dom = new JSDOM('<!doctype html><div id="root"></div><div id="app"></div>', { url: "http://localhost" });
  globalThis.window = dom.window as unknown as Window & typeof globalThis;
  globalThis.document = dom.window.document;
  (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

  const rootEl = dom.window.document.getElementById("root");
  const appEl = dom.window.document.getElementById("app");
  if (!rootEl || !appEl) throw new Error("missing root");
  return {
    appEl,
    root: createRoot(rootEl),
    restore: () => {
      globalThis.window = originalWindow;
      globalThis.document = originalDocument;
      (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = originalAct;
    },
  };
}
