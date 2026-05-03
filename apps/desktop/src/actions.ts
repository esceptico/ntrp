import {
  type AppConfig,
  apiWithConfig,
  checkHealth,
  loadInitialConfig,
  saveConfig,
  submitToolResult,
  validateConnection,
  type HistoryMessage,
  type SessionListItem,
} from "./api";
import { getState, type UiMessage } from "./store";

function formatCall(name: string, argsJson: string): string {
  try {
    const parsed = JSON.parse(argsJson || "{}");
    if (parsed && typeof parsed === "object") {
      const entries = Object.entries(parsed as Record<string, unknown>);
      if (entries.length === 0) return `${name}()`;
      const parts = entries.map(([k, v]) => {
        const val = typeof v === "string" ? `"${v}"` : JSON.stringify(v);
        return `${k}=${val}`;
      });
      const full = `${name}(${parts.join(", ")})`;
      return full.length > 120 ? `${full.slice(0, 117)}…` : full;
    }
  } catch {
    /* fall through */
  }
  return name;
}

export async function loadHistory(sessionId: string): Promise<void> {
  const s = getState();
  const { messages } = await apiWithConfig<{ messages: HistoryMessage[] }>(
    s.config,
    `/session/history?session_id=${encodeURIComponent(sessionId)}`,
  );

  const items: UiMessage[] = [];
  let activeActivityId: string | null = null;

  const findActivity = (id: string) =>
    items.find((it) => it.id === id && it.role === "activity")?.activity;

  messages.forEach((msg, index) => {
    if (msg.role === "user") {
      activeActivityId = null;
      // Historic user messages don't carry real timing, but we still want
      // the collapse UI to engage. Stamp the turn as "ended" (so isDone is
      // true) with a null durationMs (so the header shows "Worked" rather
      // than a fake "Worked for X").
      items.push({
        id: `history-${index}`,
        role: "user",
        content: msg.content,
        turn: { startedAt: 0, endedAt: 0, durationMs: null },
      });
      return;
    }

    if (msg.role === "tool") {
      return;
    }

    // assistant
    if (msg.reasoning_content) {
      activeActivityId = null;
      items.push({
        id: `history-${index}-reasoning`,
        role: "reasoning",
        title: "Reasoning",
        content: msg.reasoning_content,
      });
    }

    if (msg.content && msg.content.trim().length > 0) {
      activeActivityId = null;
      items.push({ id: `history-${index}`, role: "assistant", content: msg.content });
    }

    if (msg.tool_calls && msg.tool_calls.length > 0) {
      if (!activeActivityId) {
        activeActivityId = `history-activity-${index}`;
        items.push({
          id: activeActivityId,
          role: "activity",
          content: "",
          activity: { items: [], label: "Called", done: true },
        });
      }
      const activity = findActivity(activeActivityId);
      if (activity) {
        for (const tc of msg.tool_calls) {
          activity.items.push({
            id: tc.id,
            kind: tc.name,
            target: formatCall(tc.name, tc.arguments || "{}"),
          });
        }
      }
    }
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

  s.appendMessage({
    id: crypto.randomUUID(),
    role: "user",
    content: text.trim(),
    turn: { startedAt: Date.now(), endedAt: null, durationMs: null },
  });
  s.setRunning(true);

  try {
    await apiWithConfig<{ run_id: string }>(s.config, "/chat/message", {
      method: "POST",
      body: JSON.stringify({
        message: text.trim(),
        session_id: s.currentSessionId,
        skip_approvals: s.skipApprovals,
      }),
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

export async function respondToApproval(
  approvalId: string,
  toolId: string,
  approved: boolean,
  feedback = "",
): Promise<void> {
  const s = getState();
  if (!s.currentRunId) return;
  s.setApprovalStatus(approvalId, approved ? "approved" : "rejected");
  try {
    await submitToolResult(s.config, {
      run_id: s.currentRunId,
      tool_id: toolId,
      result: feedback,
      approved,
    });
  } catch (error) {
    s.setApprovalStatus(approvalId, "pending");
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
