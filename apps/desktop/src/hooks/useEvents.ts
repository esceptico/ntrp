import { useEffect } from "react";
import { type AppConfig, type ServerEvent } from "../api";
import { loadHistory } from "../actions/history";
import { enqueueMessage } from "../actions/messages";
import { setState, useStore } from "../store";
import {
  eventStreamUrl,
  handleIncomingServerEvent,
  lastEventSeqForSession,
  markStreamConnected,
  markStreamConnecting,
  markStreamDisconnected,
  recordTransportEventForDiagnostics,
} from "../store/chat-stream";

export {
  clearReplayGapBlockForSession,
  eventStreamUrl,
  forgetEventSeqForSession,
  handleIncomingServerEvent,
  handleReplayServerEvent,
  handleServerEvent,
  lastEventSeqForSession,
  reloadHistoryAfterReplayGap,
  resetEventSeqStateForTest,
  resetReplayGapReloadStateForTest,
  resetStreamStateForTest,
  transportDiagnosticsForSession,
} from "../store/chat-stream";

function headersFor(config: AppConfig): HeadersInit {
  return config.apiKey ? { Authorization: `Bearer ${config.apiKey}` } : {};
}

type DesktopEventsBridge = NonNullable<NonNullable<Window["ntrpDesktop"]>["events"]>;

type DesktopEventPayload = {
  connectionId: string;
  event?: unknown;
  error?: string;
  closed?: boolean;
  reason?: string;
};

interface DesktopEventStreamLoopOptions {
  desktopEvents: DesktopEventsBridge;
  config: AppConfig;
  sessionId: string;
  signal: AbortSignal;
  retryDelayMs?: number;
  getAfterSeq?: () => number | undefined;
  onEvent: (event: ServerEvent) => void | Promise<void>;
  onError: (message: string) => void;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  if (ms <= 0 || signal.aborted) return Promise.resolve();
  return new Promise((resolve) => {
    const finish = () => {
      clearTimeout(timeout);
      signal.removeEventListener("abort", finish);
      resolve();
    };
    const timeout = setTimeout(finish, ms);
    signal.addEventListener("abort", finish, { once: true });
  });
}

export async function runDesktopEventStreamLoop({
  desktopEvents,
  config,
  sessionId,
  signal,
  retryDelayMs = 1500,
  getAfterSeq,
  onEvent,
  onError,
}: DesktopEventStreamLoopOptions): Promise<void> {
  let connectionId: string | null = null;
  let resolveTerminal: ((reason: string) => void) | null = null;

  const dispose = desktopEvents.onData((payload: DesktopEventPayload) => {
    if (!connectionId || payload.connectionId !== connectionId) return;
    if (payload.event) {
      const event = payload.event as ServerEvent;
      recordTransportEventForDiagnostics(event);
      void onEvent(event);
      return;
    }
    if (payload.error) {
      markStreamDisconnected(sessionId, payload.error, payload.error);
      onError(payload.error);
      resolveTerminal?.(payload.error);
      return;
    }
    if (payload.closed) {
      markStreamDisconnected(sessionId, payload.reason ?? "closed");
      resolveTerminal?.(payload.reason ?? "closed");
    }
  });

  try {
    while (!signal.aborted) {
      const afterSeq = getAfterSeq?.() ?? lastEventSeqForSession(sessionId);
      markStreamConnecting(sessionId, afterSeq);
      try {
        connectionId = await desktopEvents.connect(config, sessionId, afterSeq);
        if (signal.aborted) break;
        markStreamConnected(sessionId);

        await new Promise<void>((resolve) => {
          const finish = () => {
            signal.removeEventListener("abort", finish);
            resolveTerminal = null;
            resolve();
          };
          resolveTerminal = finish;
          signal.addEventListener("abort", finish, { once: true });
        });
      } catch (error) {
        if (!signal.aborted) {
          const message = errorMessage(error);
          markStreamDisconnected(sessionId, message, message);
          onError(message);
        }
      } finally {
        const id = connectionId;
        connectionId = null;
        resolveTerminal = null;
        if (id) {
          try {
            await desktopEvents.disconnect(id);
          } catch {
            // Best effort cleanup; reconnect will create a fresh stream.
          }
        }
      }
      await sleep(retryDelayMs, signal);
    }
  } finally {
    dispose();
    if (connectionId) {
      try {
        await desktopEvents.disconnect(connectionId);
      } catch {
        // Best effort cleanup on unmount/abort.
      }
    }
    markStreamDisconnected(sessionId, "aborted");
  }
}

export function useEvents(sessionId: string | null) {
  const config = useStore((s) => s.config);
  const historyLoadedFor = useStore((s) => s.sessionView.historyLoadedFor);
  const historyReloadingFor = useStore((s) => s.sessionView.historyReloadingFor);
  const ready =
    sessionId !== null &&
    historyLoadedFor === sessionId &&
    historyReloadingFor !== sessionId;

  useEffect(() => {
    if (!sessionId || !ready) return;
    let disposed = false;
    const reloadHistory = (reloadSessionId: string) => loadHistory(reloadSessionId);
    const desktopEvents = window.ntrpDesktop?.events;
    if (desktopEvents) {
      const controller = new AbortController();
      void runDesktopEventStreamLoop({
        desktopEvents,
        config,
        sessionId,
        signal: controller.signal,
        onEvent: (event) => {
          void handleIncomingServerEvent(event, reloadHistory, {
            resendQueuedMessage: (text, images) => enqueueMessage(text, images ?? []),
          });
        },
        onError: (message) => {
          if (!disposed) setState({ error: message });
        },
      });

      return () => {
        disposed = true;
        controller.abort();
      };
    }

    const controller = new AbortController();
    void (async () => {
      while (!disposed && !controller.signal.aborted) {
        try {
          markStreamConnecting(sessionId, lastEventSeqForSession(sessionId));
          const response = await fetch(eventStreamUrl(config, sessionId), {
            headers: headersFor(config),
            signal: controller.signal,
          });
          if (!response.ok || !response.body) {
            throw new Error(`event stream failed: ${response.status}`);
          }
          markStreamConnected(sessionId);

          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let buffer = "";

          while (!disposed && !controller.signal.aborted) {
            const { done, value } = await reader.read();
            if (done) {
              markStreamDisconnected(sessionId, "eof");
              await new Promise((resolve) => setTimeout(resolve, 1500));
              break;
            }
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop() ?? "";
            for (const line of lines) {
              if (!line.startsWith("data: ")) continue;
              try {
                void handleIncomingServerEvent(JSON.parse(line.slice(6)) as ServerEvent, reloadHistory, {
                  resendQueuedMessage: (text, images) => enqueueMessage(text, images ?? []),
                });
              } catch {
                /* keep-alive */
              }
            }
          }
        } catch (error) {
          if (controller.signal.aborted) return;
          const message = errorMessage(error);
          markStreamDisconnected(sessionId, message, message);
          setState({ error: message });
          await new Promise((resolve) => setTimeout(resolve, 1500));
        }
      }
    })();

    return () => {
      disposed = true;
      controller.abort();
      markStreamDisconnected(sessionId);
    };
  }, [sessionId, config, ready]);
}
