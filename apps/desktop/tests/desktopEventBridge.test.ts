import { expect, test } from "bun:test";
import {
  runDesktopEventStreamLoop,
  transportDiagnosticsForSession,
} from "../src/hooks/useEvents.ts";
import type { AppConfig, ServerEvent } from "../src/api.ts";

async function waitFor(predicate: () => boolean) {
  for (let i = 0; i < 50; i += 1) {
    if (predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
  expect(predicate()).toBe(true);
}

test("desktop event bridge reconnects after close and resumes from latest seq", async () => {
  const config: AppConfig = { serverUrl: "http://localhost:6877", apiKey: "" };
  const connectCalls: Array<number | undefined> = [];
  const disconnects: string[] = [];
  let callback: ((payload: { connectionId: string; event?: ServerEvent; closed?: boolean; reason?: string }) => void) | null = null;
  let latestSeq: number | undefined;

  const controller = new AbortController();
  const loop = runDesktopEventStreamLoop({
    desktopEvents: {
      connect: async (_config, _sessionId, afterSeq) => {
        connectCalls.push(afterSeq);
        return `conn-${connectCalls.length}`;
      },
      disconnect: async (connectionId) => {
        disconnects.push(connectionId);
      },
      onData: (cb) => {
        callback = cb as typeof callback;
        return () => {
          callback = null;
        };
      },
    },
    config,
    sessionId: "sess-bridge",
    signal: controller.signal,
    retryDelayMs: 0,
    getAfterSeq: () => latestSeq,
    onEvent: (event) => {
      if (typeof event.seq === "number") latestSeq = event.seq;
    },
    onError: () => undefined,
  });

  await waitFor(() => connectCalls.length === 1);
  callback?.({
    connectionId: "conn-1",
    event: { type: "RUN_STARTED", run_id: "run-1", session_id: "sess-bridge", seq: 7 },
  });
  callback?.({ connectionId: "conn-1", closed: true, reason: "eof" });

  await waitFor(() => connectCalls.length === 2);
  expect(connectCalls).toEqual([undefined, 7]);
  expect(transportDiagnosticsForSession("sess-bridge")).toMatchObject({
    lastSeq: 7,
    connectAfterSeq: 7,
    lastClosedReason: "eof",
  });

  controller.abort();
  await loop;
  expect(disconnects).toContain("conn-2");
});
