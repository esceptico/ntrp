import {
  type AppConfig,
  apiWithConfig,
  archiveSessionApi,
  branchSessionApi,
  cancelRun,
  checkHealth,
  createAutomationApi,
  deleteAutomationApi,
  fetchSkillContent,
  getServerConfig,
  getServerModels,
  listArchivedSessionsApi,
  listAutomationsApi,
  listSkills,
  loadInitialConfig,
  patchServerConfig,
  permanentlyDeleteSessionApi,
  renameSessionApi,
  restoreSessionApi,
  runAutomationApi,
  saveConfig,
  submitToolResult,
  toggleAutomationApi,
  updateAutomationApi,
  validateConnection,
  type CreateAutomationPayload,
  type HistoryMessage,
  type ServerConfigPatch,
  type SessionListItem,
  type UpdateAutomationPayload,
} from "./api";
import { getState, type ImageBlock, type UiMessage } from "./store";
import { SEMANTIC_KIND_AGENT } from "./lib/agent";

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

  // Pre-index tool results so we can attach them to their calls regardless
  // of ordering between the assistant message and its `tool` follow-ups.
  const resultsById = new Map<string, string>();
  for (const msg of messages) {
    if (msg.role === "tool" && msg.tool_call_id) {
      resultsById.set(msg.tool_call_id, msg.content);
    }
  }

  const items: UiMessage[] = [];
  let activeActivityId: string | null = null;

  const findActivity = (id: string) =>
    items.find((it) => it.id === id && it.role === "activity")?.activity;

  messages.forEach((msg, index) => {
    // Prefer the stable server-issued id; fall back to a positional id for
    // older sessions whose messages were saved before id-based persistence.
    const stableId = msg.id ?? `history-${index}`;

    if (msg.role === "user") {
      activeActivityId = null;
      items.push({
        id: stableId,
        role: "user",
        content: msg.content,
        turn: { startedAt: 0, endedAt: 0, durationMs: null },
        images: msg.images,
      });
      return;
    }

    if (msg.role === "tool") {
      // Already folded into the matching activity item via resultsById.
      return;
    }

    // assistant
    if (msg.reasoning_content) {
      activeActivityId = null;
      items.push({
        id: `${stableId}-reasoning`,
        role: "reasoning",
        title: "Reasoning",
        content: msg.reasoning_content,
      });
    }

    if (msg.content && msg.content.trim().length > 0) {
      activeActivityId = null;
      items.push({
        id: stableId,
        role: "assistant",
        content: msg.content,
      });
    }

    if (msg.tool_calls && msg.tool_calls.length > 0) {
      if (!activeActivityId) {
        activeActivityId = `${stableId}-activity`;
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
          const args = tc.arguments || "";
          activity.items.push({
            id: tc.id,
            kind: tc.name,
            semanticKind:
              tc.kind === SEMANTIC_KIND_AGENT ? SEMANTIC_KIND_AGENT : undefined,
            target: formatCall(tc.name, args || "{}"),
            args,
            result: resultsById.get(tc.id),
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
  void fetchServerConfig();
}

export async function fetchServerConfig(): Promise<void> {
  const s = getState();
  try {
    const [cfg, models] = await Promise.all([
      getServerConfig(s.config),
      getServerModels(s.config).catch(() => null),
    ]);
    s.setServerConfig(cfg);
    if (models) s.setServerModels(models);
  } catch {
    /* server config is optional UI surface — don't surface this error */
  }
}

export async function updateServerConfig(patch: ServerConfigPatch): Promise<void> {
  const s = getState();
  const next = await patchServerConfig(s.config, patch);
  s.setServerConfig(next);
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

/** Fetch a skill's source markdown and pop the in-app viewer. Falls back to
 *  opening the file in the OS default app if the fetch fails (e.g. server
 *  is offline but the file exists locally). */
export async function viewSkill(name: string): Promise<void> {
  const s = getState();
  const skill = s.skills.find((sk) => sk.name === name);
  try {
    const data = await fetchSkillContent(s.config, name);
    s.setViewingMarkdown({
      title: skill?.name ?? data.name,
      subtitle: data.path,
      content: data.content,
      sourcePath: data.path,
    });
  } catch (error) {
    // Couldn't load via server. As a last resort, open externally if we
    // know the path locally.
    if (skill?.path) void window.ntrpDesktop?.shell?.openPath(skill.path);
    else {
      s.appendMessage({
        id: crypto.randomUUID(),
        role: "error",
        content: error instanceof Error ? error.message : String(error),
      });
    }
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

export async function renameSession(sessionId: string, name: string): Promise<void> {
  const s = getState();
  const trimmed = name.trim();
  if (!trimmed) return;
  await renameSessionApi(s.config, sessionId, trimmed);
  s.setSessions(
    s.sessions.map((sess) =>
      sess.session_id === sessionId ? { ...sess, name: trimmed } : sess,
    ),
  );
}

export async function archiveSession(sessionId: string): Promise<void> {
  const s = getState();
  await archiveSessionApi(s.config, sessionId);
  const remaining = s.sessions.filter((sess) => sess.session_id !== sessionId);
  s.setSessions(remaining);
  // Invalidate archived list so the next open re-fetches.
  s.setArchivedSessions(null);
  if (s.currentSessionId === sessionId) {
    if (remaining.length > 0) {
      await switchSession(remaining[0].session_id);
    } else {
      await createSession();
    }
  }
}

export async function fetchArchivedSessions(): Promise<void> {
  const s = getState();
  if (!s.connected) return;
  try {
    const sessions = await listArchivedSessionsApi(s.config);
    s.setArchivedSessions(sessions);
  } catch {
    s.setArchivedSessions([]);
  }
}

export async function restoreArchivedSession(sessionId: string): Promise<void> {
  const s = getState();
  await restoreSessionApi(s.config, sessionId);
  // Move back into the live sessions list — easiest is a refresh of both.
  const archived = s.archivedSessions ?? [];
  s.setArchivedSessions(archived.filter((a) => a.session_id !== sessionId));
  const { sessions } = await apiWithConfig<{ sessions: SessionListItem[] }>(s.config, "/sessions");
  s.setSessions(sessions);
}

export async function permanentlyDeleteSession(sessionId: string): Promise<void> {
  const s = getState();
  await permanentlyDeleteSessionApi(s.config, sessionId);
  const archived = s.archivedSessions ?? [];
  s.setArchivedSessions(archived.filter((a) => a.session_id !== sessionId));
}

export async function branchAtMessage(messageId: string): Promise<void> {
  const s = getState();
  if (!s.currentSessionId) return;
  const branched = await branchSessionApi(s.config, s.currentSessionId, {
    up_to_message_id: messageId,
  });
  const { sessions } = await apiWithConfig<{ sessions: SessionListItem[] }>(s.config, "/sessions");
  s.setSessions(sessions);
  await switchSession(branched.session_id);
}

export async function sendMessage(text: string, images: ImageBlock[] = []): Promise<void> {
  const s = getState();
  if (!s.currentSessionId) return;
  const trimmedText = text.trim();
  if (!trimmedText && images.length === 0) return;

  if (s.editingId) {
    // Truncate the *server's* saved message list at the message being
    // edited too — without this, the agent's next run sees both the
    // original message and the edit and the chat snowballs.
    try {
      await apiWithConfig(s.config, "/session/revert", {
        method: "POST",
        body: JSON.stringify({
          session_id: s.currentSessionId,
          message_id: s.editingId,
        }),
      });
    } catch (error) {
      s.appendMessage({
        id: crypto.randomUUID(),
        role: "error",
        content: error instanceof Error ? error.message : String(error),
      });
      return;
    }
    s.truncateFrom(s.editingId);
    s.setEditingId(null);
  }

  // Use the same id locally and on the server so /session/revert can match
  // this user message back to its saved row when the user later edits it.
  const userMessageId = crypto.randomUUID();
  s.appendMessage({
    id: userMessageId,
    role: "user",
    content: trimmedText,
    turn: { startedAt: Date.now(), endedAt: null, durationMs: null },
    images: images.length > 0 ? images : undefined,
  });
  s.setRunning(true);

  try {
    await apiWithConfig<{ run_id: string }>(s.config, "/chat/message", {
      method: "POST",
      body: JSON.stringify({
        message: trimmedText,
        session_id: s.currentSessionId,
        skip_approvals: s.skipApprovals,
        images: images.length > 0 ? images : undefined,
        client_id: userMessageId,
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

export async function stopRun(): Promise<void> {
  const s = getState();
  const runId = s.currentRunId;
  if (!runId) return;
  try {
    await cancelRun(s.config, runId);
  } catch (error) {
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

// ─── Automations ────────────────────────────────────────────────────

export async function fetchAutomations(): Promise<void> {
  const s = getState();
  try {
    const automations = await listAutomationsApi(s.config);
    s.setAutomations(automations);
  } catch {
    /* leave previous list in place */
  }
}

export async function createAutomation(payload: CreateAutomationPayload): Promise<void> {
  const s = getState();
  await createAutomationApi(s.config, payload);
  await fetchAutomations();
}

export async function updateAutomation(taskId: string, patch: UpdateAutomationPayload): Promise<void> {
  const s = getState();
  await updateAutomationApi(s.config, taskId, patch);
  await fetchAutomations();
}

export async function toggleAutomation(taskId: string): Promise<void> {
  const s = getState();
  await toggleAutomationApi(s.config, taskId);
  await fetchAutomations();
}

export async function runAutomation(taskId: string): Promise<void> {
  const s = getState();
  await runAutomationApi(s.config, taskId);
  await fetchAutomations();
}

export async function deleteAutomation(taskId: string): Promise<void> {
  const s = getState();
  await deleteAutomationApi(s.config, taskId);
  await fetchAutomations();
}
