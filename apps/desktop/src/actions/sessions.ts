import {
  apiWithConfig,
  archiveSessionApi,
  branchSessionApi,
  listArchivedSessionsApi,
  permanentlyDeleteSessionApi,
  renameSessionApi,
  restoreSessionApi,
  type SessionListItem,
} from "../api";
import { getState } from "../store";
import { fetchGoal } from "./goals";
import { loadHistory, type LoadHistoryOptions } from "./history";

export async function switchSession(sessionId: string, historyOptions: LoadHistoryOptions = {}): Promise<void> {
  const s = getState();
  s.setCurrentSession(sessionId);
  // Cache is only a fast visual restore. Always reconcile with canonical
  // history so a stale/corrupted projection cannot survive until Cmd+R.
  await loadHistory(sessionId, historyOptions);
  await fetchGoal(sessionId);
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
