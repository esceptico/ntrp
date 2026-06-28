import { expect, test } from "bun:test";
import {
  eventStreamReadyForSession,
  reconnectDelayMs,
  runDesktopEventStreamLoop,
  transportDiagnosticsForSession,
} from "@/hooks/useEvents";
import type { AppConfig, ServerEvent } from "@/api";

test("reconnectDelayMs uses capped exponential backoff with bounded jitter", () => {
  expect(reconnectDelayMs(0, { baseMs: 500, random: () => 0.5 })).toBe(500);
  expect(reconnectDelayMs(1, { baseMs: 500, random: () => 0.5 })).toBe(1000);
  expect(reconnectDelayMs(10, { baseMs: 500, maxMs: 15_000, random: () => 0.5 })).toBe(15_000);
  expect(reconnectDelayMs(0, { baseMs: 500, random: () => 0 })).toBe(400);
  expect(reconnectDelayMs(0, { baseMs: 500, random: () => 1 })).toBe(600);
});

test("event stream stays mounted during replay-gap history reload", () => {
  expect(eventStreamReadyForSession({
    sessionId: "sess-1",
    historyLoadedFor: "sess-1",
  })).toBe(true);
  expect(eventStreamReadyForSession({
    sessionId: "sess-1",
    historyLoadedFor: null,
  })).toBe(false);
});

async function waitFor(predicate: () => boolean) {
  for (let i = 0; i < 50; i += 1) {
    if (predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
  expect(predicate()).toBe(true);
}

test("desktop event bridge marks a closed stream as reconnecting during backoff", async () => {
  const config: AppConfig = { serverUrl: "http://localhost:6877", apiKey: "" };
  let callback: ((payload: { connectionId: string; closed?: boolean; reason?: string }) => void) | null = null;

  const controller = new AbortController();
  const loop = runDesktopEventStreamLoop({
    desktopEvents: {
      connect: async () => "conn-1",
      disconnect: async () => undefined,
      onData: (cb) => {
        callback = cb as typeof callback;
        return () => {
          callback = null;
        };
      },
    },
    config,
    sessionId: "sess-backoff",
    signal: controller.signal,
    retryDelayMs: 50,
    onEvent: () => undefined,
    onError: () => undefined,
  });

  await waitFor(() => transportDiagnosticsForSession("sess-backoff")?.connectionPhase === "connected");
  callback?.({ connectionId: "conn-1", closed: true, reason: "eof" });
  await waitFor(() => transportDiagnosticsForSession("sess-backoff")?.connectionPhase === "reconnecting");

  expect(transportDiagnosticsForSession("sess-backoff")).toMatchObject({
    connectionPhase: "reconnecting",
    lastClosedReason: "eof",
  });

  controller.abort();
  await loop;
});

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
