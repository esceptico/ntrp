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
