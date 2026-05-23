import { beforeEach, expect, test } from "bun:test";

import { loadHistory } from "../src/actions/history.ts";
import { getState, setState } from "../src/store/index.ts";

beforeEach(() => {
  setState({
    messages: new Map(),
    order: [],
    activeActivityId: null,
    running: false,
    currentRunId: null,
    currentSessionId: null,
    error: null,
    skipApprovals: false,
    pendingApprovals: [],
    queuedMessages: [],
  });
});

test("loadHistory reapplies local Auto to active runtime and hides stale approvals", async () => {
  const originalWindow = (globalThis as typeof globalThis & { window?: unknown }).window;
  const requests: { path: string; method?: string; body?: string }[] = [];
  (globalThis as typeof globalThis & { window?: unknown }).window = {
    ntrpDesktop: {
      api: {
        request: async (_config: unknown, request: { path: string; method?: string; body?: string }) => {
          requests.push(request);
          const sessionId = request.path.startsWith("/session/history")
            ? new URLSearchParams(request.path.split("?")[1] ?? "").get("session_id") ?? "auto-session"
            : "auto-session";
          return {
            ok: true,
            status: 200,
            statusText: "OK",
            contentType: "application/json",
            data: request.path.startsWith("/session/history")
              ? {
                  messages: [],
                  active_run_id: "run-auto",
                  runtime: {
                    session_id: sessionId,
                    latest_event_seq: 7,
                    checkpoint_seq: 7,
                    active_run: { run_id: "run-auto", status: "running" },
                    pending_approvals: [
                      {
                        tool_id: "tool-1",
                        tool_name: "Bash",
                        preview: "date",
                        diff: null,
                        status: "pending",
                      },
                    ],
                    queued_messages: [],
                  },
                }
              : { status: "ok", skip_approvals: true, auto_resolved: 1 },
            text: "",
          };
        },
      },
    },
    setTimeout,
    clearTimeout,
  };

  try {
    setState({
      config: { serverUrl: "http://localhost:6877", apiKey: "" },
      currentSessionId: "auto-session",
      skipApprovals: true,
    });

    await loadHistory("auto-session");

    expect(getState().pendingApprovals).toEqual([]);
    expect(
      requests.some(
        (request) =>
          request.path === "/sessions/auto-session/auto" &&
          request.method === "POST" &&
          request.body === JSON.stringify({ value: true }),
      ),
    ).toBe(true);

    requests.length = 0;
    setState({
      currentSessionId: "manual-session",
      skipApprovals: false,
      pendingApprovals: [],
    });

    await loadHistory("manual-session");

    expect(getState().pendingApprovals).toMatchObject([{ toolId: "tool-1", status: "pending" }]);
    expect(requests.some((request) => request.path === "/sessions/manual-session/auto")).toBe(false);
  } finally {
    (globalThis as typeof globalThis & { window?: unknown }).window = originalWindow;
  }
});

test("loadHistory keeps active run tail activity open while a tool is being called", async () => {
  const originalWindow = (globalThis as typeof globalThis & { window?: unknown }).window;
  (globalThis as typeof globalThis & { window?: unknown }).window = {
    ntrpDesktop: {
      api: {
        request: async () => ({
          ok: true,
          status: 200,
          statusText: "OK",
          contentType: "application/json",
          data: {
            messages: [
              { role: "user", content: "inspect", id: "user-1" },
              {
                role: "assistant",
                content: "",
                id: "assistant-tool-1",
                tool_calls: [{ id: "tool-1", name: "ReadFile", arguments: '{"path":"a"}' }],
              },
            ],
            active_run_id: "run-active",
            runtime: {
              session_id: "tool-active-session",
              latest_event_seq: 4,
              checkpoint_seq: 4,
              active_run: { run_id: "run-active", status: "running" },
              pending_approvals: [],
              queued_messages: [],
            },
            page: { has_more_before: false, has_more_after: false },
          },
          text: "",
        }),
      },
    },
    setTimeout,
    clearTimeout,
  };

  try {
    setState({
      config: { serverUrl: "http://localhost:6877", apiKey: "" },
      currentSessionId: "tool-active-session",
    });

    await loadHistory("tool-active-session");

    const state = getState();
    const activityId = state.order.find((id) => state.messages.get(id)?.role === "activity");
    expect(state.sessionView.historyLoadedFor).toBe("tool-active-session");
    expect(state.activeActivityId).toBe(activityId);
    expect(state.messages.get(activityId!)?.activity).toMatchObject({
      done: false,
      label: "Calling",
      items: [{ id: "tool-1", status: "ongoing" }],
    });
  } finally {
    (globalThis as typeof globalThis & { window?: unknown }).window = originalWindow;
  }
});
