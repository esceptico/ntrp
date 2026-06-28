import { apiWithConfig } from "@/api";
import { getState, type ServerLoop } from "@/stores";
import { enqueueMessage, sendMessage } from "@/actions/messages";
import { appendError, appendStatus, truncatePrompt } from "@/actions/_shared";

export async function stopLoop(taskId: string): Promise<void> {
  const s = getState();
  const loop = s.loops.find((item) => item.task_id === taskId);

  // No active session — fall back to the direct DELETE so clicking X from
  // a stale view doesn't dispatch a message to whatever session is
  // currently focused.
  if (!s.currentSessionId) {
    try {
      await apiWithConfig(s.config, `/loops/${taskId}`, { method: "DELETE" });
      if (loop) appendStatus(`Loop stopped · ${truncatePrompt(loop.prompt)}`);
    } catch (error) {
      appendError(error instanceof Error ? error.message : String(error));
    }
    return;
  }

  // Agentic path: drop a user message into the chat asking the agent to
  // call delete_automation. The action stays visible in the transcript,
  // and the next refreshLoops poll removes the chip.
  const text = `Cancel the recurring loop with task_id "${taskId}" by calling delete_automation, then confirm in one short sentence.`;
  if (s.running) {
    await enqueueMessage(text);
  } else {
    await sendMessage(text);
  }
}

/** Toggle Auto (skip approvals) for the current session.
 *
 *  Auto state is client-owned. The local store drives the chip and the next
 *  request body; the server endpoint only mirrors it into the active run's
 *  execution controls. */
export async function toggleAuto(value: boolean): Promise<void> {
  const s = getState();
  s.setSkipApprovals(value);
  if (value) {
    // Optimistic: server auto-resolves the awaiting Futures, the cards
    // would linger here without a clear. Wipe immediately so the UI
    // reflects the toggle.
    const pending = [...s.pendingApprovals];
    for (const a of pending) s.resolvePendingApproval(a.toolId);
  }
  if (!s.currentSessionId) return;
  try {
    await apiWithConfig(s.config, `/sessions/${s.currentSessionId}/auto`, {
      method: "POST",
      body: JSON.stringify({ value }),
    });
  } catch (error) {
    // Don't roll back the local toggle — the user clearly expressed
    // intent; the next message they send will still carry skip_approvals,
    // and a server reconnect / next run picks up the right value. Just
    // surface the failure so they know.
    appendError(error instanceof Error ? error.message : String(error));
  }
}

export async function refreshLoops(sessionId: string): Promise<void> {
  const s = getState();
  try {
    const { loops } = await apiWithConfig<{ loops: ServerLoop[] }>(
      s.config,
      `/loops?session_id=${encodeURIComponent(sessionId)}`,
    );
    s.setLoops(loops);
  } catch {
    // Silent: loops are best-effort UI state; the server is the source of
    // truth. A transient fetch failure shouldn't error-spam the transcript.
  }
}
