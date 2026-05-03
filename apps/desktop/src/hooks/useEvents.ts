import { useEffect } from "react";
import { type AppConfig, type ServerEvent } from "../api";
import { getState, setState, useStore } from "../store";

function handleServerEvent(event: ServerEvent) {
  const s = getState();
  switch (event.type) {
    case "run_started":
      setState({ running: true, error: null });
      return;
    case "run_finished":
      if (event.usage) s.accumulateUsage(event.usage);
      setState({ running: false });
      return;
    case "run_error":
      s.appendMessage({ id: crypto.randomUUID(), role: "error", content: event.message });
      setState({ running: false });
      return;
    case "text":
    case "text_delta": {
      const lastId = s.order[s.order.length - 1];
      const last = lastId ? s.messages.get(lastId) : null;
      if (last && last.role === "assistant") {
        s.mutateMessage(last.id, { content: last.content + event.content });
      } else {
        s.appendMessage({ id: crypto.randomUUID(), role: "assistant", content: event.content });
      }
      return;
    }
    case "REASONING_MESSAGE_START":
      s.appendMessage({ id: event.messageId, role: "reasoning", title: "Reasoning", content: "" });
      return;
    case "REASONING_MESSAGE_CONTENT": {
      const m = s.messages.get(event.messageId);
      if (m) s.mutateMessage(event.messageId, { content: m.content + event.delta });
      else s.appendMessage({ id: event.messageId, role: "reasoning", title: "Reasoning", content: event.delta });
      return;
    }
    case "tool_call":
      s.appendMessage({
        id: event.tool_id,
        role: "tool",
        title: event.name,
        subtitle: event.description ?? "",
        content: "",
      });
      return;
    case "tool_result": {
      const content = event.preview ?? event.result ?? "done";
      if (s.messages.has(event.tool_id)) {
        s.mutateMessage(event.tool_id, { content });
      } else {
        s.appendMessage({
          id: event.tool_id,
          role: "tool",
          title: event.name,
          subtitle: "",
          content,
        });
      }
      return;
    }
    case "background_task":
      s.appendMessage({
        id: crypto.randomUUID(),
        role: "status",
        title: event.command,
        content: event.detail ? `${event.status}: ${event.detail}` : event.status,
      });
      return;
  }
}

function headersFor(config: AppConfig): HeadersInit {
  return config.apiKey ? { Authorization: `Bearer ${config.apiKey}` } : {};
}

export function useEvents(sessionId: string | null) {
  const config = useStore((s) => s.config);

  useEffect(() => {
    if (!sessionId) return;
    let disposed = false;

    const desktopEvents = window.ntrpDesktop?.events;
    if (desktopEvents) {
      let connectionId: string | null = null;
      const dispose = desktopEvents.onData((payload) => {
        if (!connectionId || payload.connectionId !== connectionId) return;
        if (payload.error) {
          setState({ error: payload.error });
          return;
        }
        if (payload.event) handleServerEvent(payload.event as ServerEvent);
      });

      void desktopEvents
        .connect(config, sessionId)
        .then((id) => {
          if (disposed) {
            void desktopEvents.disconnect(id);
            return;
          }
          connectionId = id;
        })
        .catch((error) => {
          if (!disposed) setState({ error: error instanceof Error ? error.message : String(error) });
        });

      return () => {
        disposed = true;
        dispose();
        if (connectionId) void desktopEvents.disconnect(connectionId);
      };
    }

    const controller = new AbortController();
    void (async () => {
      while (!disposed && !controller.signal.aborted) {
        try {
          const response = await fetch(
            `${config.serverUrl}/chat/events/${encodeURIComponent(sessionId)}?stream=true`,
            { headers: headersFor(config), signal: controller.signal },
          );
          if (!response.ok || !response.body) throw new Error(`event stream failed: ${response.status}`);

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
                handleServerEvent(JSON.parse(line.slice(6)) as ServerEvent);
              } catch {
                /* keep-alive */
              }
            }
          }
        } catch (error) {
          if (controller.signal.aborted) return;
          setState({ error: error instanceof Error ? error.message : String(error) });
          await new Promise((resolve) => setTimeout(resolve, 1500));
        }
      }
    })();

    return () => {
      disposed = true;
      controller.abort();
    };
  }, [sessionId, config]);
}
