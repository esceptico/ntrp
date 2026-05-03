import {
  type AppConfig,
  apiWithConfig,
  checkHealth,
  loadInitialConfig,
  saveConfig,
  validateConnection,
  type HistoryMessage,
  type SessionListItem,
} from "./api";
import { getState, type Role, type UiMessage } from "./store";

export async function loadHistory(sessionId: string): Promise<void> {
  const s = getState();
  const { messages } = await apiWithConfig<{ messages: HistoryMessage[] }>(
    s.config,
    `/session/history?session_id=${encodeURIComponent(sessionId)}`,
  );

  const items: UiMessage[] = [];
  messages.forEach((msg, index) => {
    if (msg.reasoning_content) {
      items.push({
        id: `history-${index}-reasoning`,
        role: "reasoning",
        title: "Reasoning",
        content: msg.reasoning_content,
      });
    }
    items.push({
      id: `history-${index}`,
      role: msg.role as Role,
      content: msg.content,
    });
  });
  s.setHistory(items);
}

export async function refresh(): Promise<void> {
  const s = getState();
  try {
    const health = await checkHealth(s.config);
    if (!health.ok) {
      throw new Error(health.version ? "Invalid API key" : "Could not reach ntrp server");
    }
    s.setConnected(true);
    s.setError(null);

    const [{ sessions }, session] = await Promise.all([
      apiWithConfig<{ sessions: SessionListItem[] }>(s.config, "/sessions"),
      apiWithConfig<{ session_id: string; name?: string | null }>(s.config, "/session"),
    ]);
    s.setSessions(sessions);
    s.setCurrentSession(session.session_id);
    await loadHistory(session.session_id);
  } catch (error) {
    s.setConnected(false);
    s.setError(error instanceof Error ? error.message : String(error));
  }
}

export async function bootstrap(): Promise<void> {
  const s = getState();
  try {
    const config = await loadInitialConfig();
    s.setConfig(config);
  } catch (error) {
    s.setError(error instanceof Error ? error.message : String(error));
  }
  await refresh();
}

export async function switchSession(sessionId: string): Promise<void> {
  const s = getState();
  s.setCurrentSession(sessionId);
  await loadHistory(sessionId);
}

export async function createSession(): Promise<void> {
  const s = getState();
  const session = await apiWithConfig<SessionListItem>(s.config, "/sessions", {
    method: "POST",
    body: "{}",
  });
  s.prependSession(session);
  await switchSession(session.session_id);
}

export async function sendMessage(text: string): Promise<void> {
  const s = getState();
  if (!s.currentSessionId || !text.trim()) return;

  if (s.editingId) {
    s.truncateFrom(s.editingId);
    s.setEditingId(null);
  }

  s.appendMessage({ id: crypto.randomUUID(), role: "user", content: text.trim() });
  s.setRunning(true);

  try {
    await apiWithConfig<{ run_id: string }>(s.config, "/chat/message", {
      method: "POST",
      body: JSON.stringify({ message: text.trim(), session_id: s.currentSessionId }),
    });
  } catch (error) {
    s.setRunning(false);
    s.appendMessage({
      id: crypto.randomUUID(),
      role: "error",
      content: error instanceof Error ? error.message : String(error),
    });
  }
}

export async function saveAndReconnect(next: AppConfig): Promise<void> {
  const s = getState();
  s.setConnectionSaving(true);
  s.setConnectionError(null);
  try {
    await validateConnection(next);
    const saved = await saveConfig(next);
    s.setConfig(saved);
    s.closeSettings();
    await refresh();
  } catch (error) {
    s.setConnectionError(error instanceof Error ? error.message : String(error));
  } finally {
    s.setConnectionSaving(false);
  }
}
