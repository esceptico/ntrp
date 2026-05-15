import {
  apiWithConfig,
  cancelQueuedMessageApi,
  cancelRun,
} from "../api";
import { getState, setState, type ImageBlock } from "../store";
import { messagesScroll } from "../lib/messagesScroll";
import {
  reduceRunCompleted,
  reduceRunFailed,
  reduceRunStarted,
  reduceRunStopCleared,
  reduceRunStopRequested,
} from "../store/run-lifecycle";
import { clearCachedStoppingRun } from "../store/session-cache";

export async function sendMessage(text: string, images: ImageBlock[] = []): Promise<void> {
  const s = getState();
  if (!s.currentSessionId) return;
  const sendSessionId = s.currentSessionId;
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
          session_id: sendSessionId,
          message_id: s.editingId,
        }),
      });
    } catch (error) {
      if (getState().currentSessionId === sendSessionId) {
        s.appendMessage({
          id: crypto.randomUUID(),
          role: "error",
          content: error instanceof Error ? error.message : String(error),
        });
      }
      return;
    }
    if (getState().currentSessionId !== sendSessionId) return;
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
  messagesScroll.scrollToBottom?.("smooth");
  setState((state) =>
    reduceRunStarted(state, { runId: null, sessionId: sendSessionId }),
  );

  try {
    const response = await apiWithConfig<{ run_id: string }>(s.config, "/chat/message", {
      method: "POST",
      body: JSON.stringify({
        message: trimmedText,
        session_id: sendSessionId,
        skip_approvals: s.skipApprovals,
        images: images.length > 0 ? images : undefined,
        client_id: userMessageId,
      }),
    });
    setState((state) =>
      reduceRunStarted(state, { runId: response.run_id, sessionId: sendSessionId }),
    );
  } catch (error) {
    setState((state) =>
      reduceRunFailed(state, { runId: null, sessionId: sendSessionId }),
    );
    if (getState().currentSessionId === sendSessionId) {
      s.appendMessage({
        id: crypto.randomUUID(),
        role: "error",
        content: error instanceof Error ? error.message : String(error),
      });
    }
  }
}

/** Submit a message while a run is in flight. Server queues it onto the
 *  active run's inject_queue; we render it as a "Queued" bubble above
 *  the composer until `message_ingested` arrives. */
export async function enqueueMessage(text: string, images: ImageBlock[] = []): Promise<void> {
  const s = getState();
  if (!s.currentSessionId) return;
  const trimmed = text.trim();
  if (!trimmed && images.length === 0) return;

  const clientId = crypto.randomUUID();
  s.addQueuedMessage({
    clientId,
    text: trimmed,
    images: images.length > 0 ? images : undefined,
    status: "pending",
    enqueuedAt: Date.now(),
  });

  try {
    await apiWithConfig<{ run_id: string }>(s.config, "/chat/message", {
      method: "POST",
      body: JSON.stringify({
        message: trimmed,
        session_id: s.currentSessionId,
        skip_approvals: s.skipApprovals,
        images: images.length > 0 ? images : undefined,
        client_id: clientId,
      }),
    });
  } catch {
    s.setQueuedMessageStatus(clientId, "failed");
  }
}

/** Cancel a queued (not yet ingested) message. The server returns:
 *    cancelled         — removed; we drop the bubble
 *    already_ingested  — too late, the agent has it; the imminent
 *                        message_ingested event will absorb the bubble
 *    no_run            — no active run, drop the bubble */
export async function cancelQueuedMessage(clientId: string): Promise<void> {
  const s = getState();
  if (!s.currentSessionId) return;
  s.setQueuedMessageStatus(clientId, "cancelling");
  let result;
  try {
    result = await cancelQueuedMessageApi(s.config, s.currentSessionId, clientId);
  } catch {
    s.setQueuedMessageStatus(clientId, "pending");
    return;
  }
  if (result === "cancelled" || result === "no_run") {
    s.removeQueuedMessage(clientId);
  } else {
    s.setQueuedMessageStatus(clientId, "sent");
  }
}

export async function stopRun(): Promise<void> {
  const s = getState();
  const runId = s.currentRunId;
  const sessionId = s.currentSessionId;
  if (!runId) return;
  setState((state) => reduceRunStopRequested(state, runId));
  const clearStoppedRun = () => {
    setState((state) =>
      reduceRunCompleted(state, {
        runId,
        sessionId,
      }),
    );
  };
  try {
    await cancelRun(s.config, runId);
    clearStoppedRun();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (message === "Run not found") {
      clearStoppedRun();
      return;
    }
    setState((state) => ({
      ...reduceRunStopCleared(state, runId),
      ...clearCachedStoppingRun(state, sessionId, runId),
    }));
    if (getState().currentSessionId === sessionId) {
      s.appendMessage({
        id: crypto.randomUUID(),
        role: "error",
        content: message,
      });
    }
  }
}
