import { apiWithConfig, checkHealth, listProjectsApi, loadInitialConfig, type SessionListItem } from "../api";
import { getState } from "../store";
import { fetchAutomations } from "./automations";
import { fetchGoal } from "./goals";
import { loadHistory } from "./history";
import { refreshLoops } from "./loops";
import { refreshSessions } from "./sessions";
import { fetchSkills } from "./skills";
import { fetchServerConfig } from "./server";

const RESYNC_DEBOUNCE_MS = 800;
let resyncTimer: ReturnType<typeof setTimeout> | null = null;

/** Re-fetch the collections that have no live SSE delta feed (sessions list,
 *  automations, loops, goal, server config) after a chat-stream (re)connect or
 *  server restart. Live deltas remain the fast path; this is the correctness
 *  backstop so nothing stays stale until a manual reload. Debounced so flappy
 *  reconnects collapse into one resync. */
export function reloadAllCollections(sessionId: string | null): void {
  if (resyncTimer) clearTimeout(resyncTimer);
  resyncTimer = setTimeout(() => {
    resyncTimer = null;
    void refreshSessions();
    void fetchAutomations();
    void fetchServerConfig();
    if (sessionId) {
      void refreshLoops(sessionId);
      void fetchGoal(sessionId).catch(() => {});
    }
  }, RESYNC_DEBOUNCE_MS);
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

    const [projects, { sessions }, session] = await Promise.all([
      listProjectsApi(s.config),
      apiWithConfig<{ sessions: SessionListItem[] }>(s.config, "/sessions?limit=500"),
      apiWithConfig<{ session_id: string; name?: string | null }>(s.config, "/session"),
    ]);
    s.setProjects(projects);
    s.setSessions(sessions);
    s.setCurrentSession(session.session_id);
    await loadHistory(session.session_id);
    try {
      await fetchGoal(session.session_id);
    } catch {
      // Goal state is accessory UI; history/session refresh should remain usable.
    }
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
  // Seed the collections that otherwise stay empty/stale until their first
  // poll or an event arrives (the automations card + loop countdowns).
  void fetchAutomations();
  const sessionId = getState().currentSessionId;
  if (sessionId) void refreshLoops(sessionId);
}
