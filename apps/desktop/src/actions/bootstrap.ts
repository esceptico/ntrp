import { apiWithConfig, checkHealth, listPrimarySessionsApi, listProjectsApi, loadInitialConfig } from "@/api";
import { getState } from "@/store";
import { isAgentSessionId, parentSessionIdOf } from "@/lib/agentRun";
import { fetchAutomations } from "@/actions/automations";
import { refreshChildAgents } from "@/actions/childAgents";
import { fetchGoal } from "@/actions/goals";
import { loadHistory } from "@/actions/history";
import { refreshLoops } from "@/actions/loops";
import { refreshSessions } from "@/actions/sessions";
import { fetchSkills } from "@/actions/skills";
import { fetchServerConfig } from "@/actions/server";

const RESYNC_DEBOUNCE_MS = 800;
// Don't resync more than once per window: under reconnect churn (a busy server
// delaying keepalives, rapid session switches) onConnect can fire repeatedly,
// and we must not stampede an already-loaded server with 5-fetch bursts.
const RESYNC_MIN_INTERVAL_MS = 8_000;
let resyncTimer: ReturnType<typeof setTimeout> | null = null;
let lastResyncAt = 0;

/** Re-fetch the collections that have no live SSE delta feed (sessions list,
 *  automations, loops, goal, server config) after a chat-stream (re)connect or
 *  server restart. Live deltas remain the fast path; this is the correctness
 *  backstop so nothing stays stale until a manual reload. Debounced + rate-
 *  limited so flappy reconnects collapse into one resync. */
export function reloadAllCollections(sessionId: string | null): void {
  if (Date.now() - lastResyncAt < RESYNC_MIN_INTERVAL_MS) return;
  if (resyncTimer) clearTimeout(resyncTimer);
  resyncTimer = setTimeout(() => {
    resyncTimer = null;
    lastResyncAt = Date.now();
    // Session-agnostic collections always reflect current truth.
    void refreshSessions();
    void fetchAutomations();
    void fetchServerConfig();
    // Per-session refreshes only if this is STILL the active session — the
    // debounce can outlive a session switch / unmount, and must not write a
    // stale session's loops/goal into the store.
    if (sessionId && getState().currentSessionId === sessionId) {
      void refreshLoops(sessionId);
      void fetchGoal(sessionId).catch(() => {});
      // The background-agent roster has live deltas (BackgroundTaskEvent) but no
      // replay on reconnect, so resync it here for the session whose roster the
      // sidebar shows (the parent when a child agent is open).
      const rosterSessionId = isAgentSessionId(sessionId) ? parentSessionIdOf(sessionId) : sessionId;
      if (rosterSessionId) void refreshChildAgents(rosterSessionId);
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

    const [projects, sessions, session] = await Promise.all([
      listProjectsApi(s.config),
      listPrimarySessionsApi(s.config),
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
