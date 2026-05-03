import {
  type AppConfig,
  apiWithConfig,
  checkHealth,
  listSkills,
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
  void fetchSkills();
}

export async function fetchSkills(): Promise<void> {
  const s = getState();
  try {
    const skills = await listSkills(s.config);
    s.setSkills(skills);
  } catch {
    /* skills are optional — don't surface an error */
  }
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

// ─── Builtin slash-commands ──────────────────────────────────────────

export interface BuiltinCommand {
  name: string;
  description: string;
  /** Hidden commands aren't surfaced in the picker but are still routable
   *  via dispatchCommand when typed manually. Reserved for things that
   *  require an arg (e.g. /rename) so they don't muddy the visual list. */
  hidden?: boolean;
}

export const BUILTIN_COMMANDS: BuiltinCommand[] = [
  { name: "clear", description: "Clear this session's messages" },
  { name: "compact", description: "Compact context window" },
  { name: "revert", description: "Revert one turn" },
  { name: "branch", description: "Branch into a new session" },
  { name: "rename", description: "Rename this session", hidden: true },
  { name: "cost", description: "Show usage so far" },
];

const BUILTIN_NAMES = new Set(BUILTIN_COMMANDS.map((c) => c.name));

export function isBuiltin(name: string): boolean {
  return BUILTIN_NAMES.has(name);
}

function appendStatus(content: string): void {
  getState().appendMessage({
    id: crypto.randomUUID(),
    role: "status",
    content,
  });
}

function appendError(content: string): void {
  getState().appendMessage({
    id: crypto.randomUUID(),
    role: "error",
    content,
  });
}

function formatTokens(n: number): string {
  if (n < 1000) return `${n}`;
  if (n < 10000) return `${(n / 1000).toFixed(1)}k`;
  return `${Math.round(n / 1000)}k`;
}

function formatCost(n: number): string {
  return n < 0.01 ? `$${n.toFixed(4)}` : `$${n.toFixed(3)}`;
}

export async function runBuiltinCommand(name: string, args: string): Promise<void> {
  const s = getState();
  switch (name) {
    case "cost": {
      const u = s.usage;
      appendStatus(
        `Last context: ${formatTokens(u.lastPrompt)} tokens · Total: ${formatTokens(u.totalTokens)} tokens · ${formatCost(u.totalCost)}`,
      );
      return;
    }
    case "clear": {
      if (!s.currentSessionId) return;
      try {
        await apiWithConfig(s.config, "/session/clear", {
          method: "POST",
          body: JSON.stringify({ session_id: s.currentSessionId }),
        });
        s.setHistory([]);
        s.resetUsage();
      } catch (error) {
        appendError(error instanceof Error ? error.message : String(error));
      }
      return;
    }
    case "compact": {
      if (!s.currentSessionId) return;
      try {
        await apiWithConfig(s.config, "/compact", {
          method: "POST",
          body: JSON.stringify({ session_id: s.currentSessionId }),
        });
        await loadHistory(s.currentSessionId);
        appendStatus("Context compacted.");
      } catch (error) {
        appendError(error instanceof Error ? error.message : String(error));
      }
      return;
    }
    case "revert": {
      if (!s.currentSessionId) return;
      const n = parseInt(args, 10);
      const turns = Number.isFinite(n) && n > 0 ? n : 1;
      try {
        await apiWithConfig(s.config, "/session/revert", {
          method: "POST",
          body: JSON.stringify({ session_id: s.currentSessionId, turns }),
        });
        await loadHistory(s.currentSessionId);
        appendStatus(`Reverted ${turns} turn${turns === 1 ? "" : "s"}.`);
      } catch (error) {
        appendError(error instanceof Error ? error.message : String(error));
      }
      return;
    }
    case "rename": {
      if (!s.currentSessionId) return;
      const name = args.trim();
      if (!name) {
        appendError("Usage: /rename <name>");
        return;
      }
      try {
        await apiWithConfig(s.config, `/sessions/${s.currentSessionId}`, {
          method: "PATCH",
          body: JSON.stringify({ name }),
        });
        s.setSessions(
          s.sessions.map((sess) =>
            sess.session_id === s.currentSessionId ? { ...sess, name } : sess,
          ),
        );
        appendStatus(`Renamed to "${name}".`);
      } catch (error) {
        appendError(error instanceof Error ? error.message : String(error));
      }
      return;
    }
    case "branch": {
      if (!s.currentSessionId) return;
      const name = args.trim();
      try {
        const branched = await apiWithConfig<SessionListItem>(
          s.config,
          `/sessions/${s.currentSessionId}/branch`,
          {
            method: "POST",
            body: JSON.stringify(name ? { name } : {}),
          },
        );
        const { sessions } = await apiWithConfig<{ sessions: SessionListItem[] }>(
          s.config,
          "/sessions",
        );
        s.setSessions(sessions);
        await switchSession(branched.session_id);
      } catch (error) {
        appendError(error instanceof Error ? error.message : String(error));
      }
      return;
    }
  }
}

// ─── Settings ────────────────────────────────────────────────────────

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
