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
} from "../store/chat-stream";

function headersFor(config: AppConfig): HeadersInit {
  return config.apiKey ? { Authorization: `Bearer ${config.apiKey}` } : {};
}

export function useEvents(sessionId: string | null) {
  const config = useStore((s) => s.config);
  const historyLoadedFor = useStore((s) => s.historyLoadedFor);
  const historyReloadingFor = useStore((s) => s.historyReloadingFor);
  const ready =
    sessionId !== null &&
    historyLoadedFor === sessionId &&
    historyReloadingFor !== sessionId;

  useEffect(() => {
    if (!sessionId || !ready) return;
    let disposed = false;
    const reloadHistory = (reloadSessionId: string) => loadHistory(reloadSessionId);
    markStreamConnecting(sessionId);

    const desktopEvents = window.ntrpDesktop?.events;
    if (desktopEvents) {
      let connectionId: string | null = null;
      const dispose = desktopEvents.onData((payload) => {
        if (!connectionId || payload.connectionId !== connectionId) return;
        if (payload.error) {
          setState({ error: payload.error });
          return;
        }
        if (payload.event) {
          void handleIncomingServerEvent(payload.event as ServerEvent, reloadHistory, {
            resendQueuedMessage: (text, images) => enqueueMessage(text, images ?? []),
          });
        }
      });

      void desktopEvents
        .connect(config, sessionId, lastEventSeqForSession(sessionId))
        .then((id) => {
          if (disposed) {
            void desktopEvents.disconnect(id);
            return;
          }
          connectionId = id;
          markStreamConnected(sessionId);
        })
        .catch((error) => {
          if (!disposed) {
            markStreamDisconnected(sessionId);
            setState({ error: error instanceof Error ? error.message : String(error) });
          }
        });

      return () => {
        disposed = true;
        dispose();
        if (connectionId) void desktopEvents.disconnect(connectionId);
        markStreamDisconnected(sessionId);
      };
    }

    const controller = new AbortController();
    void (async () => {
      while (!disposed && !controller.signal.aborted) {
        try {
          markStreamConnecting(sessionId);
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
            if (done) break;
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
          markStreamDisconnected(sessionId);
          setState({ error: error instanceof Error ? error.message : String(error) });
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
