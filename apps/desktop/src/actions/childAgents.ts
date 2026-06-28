import { listChildAgentsApi } from "@/api";
import { childAgentTaskToBackgroundSnapshot } from "@/lib/agentRun";
import { getState } from "@/stores";

/** Fetch the durable child-agent roster for a session and write it into the
 *  store. Used by the sidebar poll AND the reconnect resync (reloadAllCollections)
 *  so an agent that started/finished while disconnected is reflected immediately
 *  on reconnect instead of waiting for the next poll tick. */
export async function refreshChildAgents(sessionId: string): Promise<void> {
  const s = getState();
  s.backgroundAgentsRefreshStarted();
  try {
    const tasks = await listChildAgentsApi(s.config, sessionId);
    s.setBackgroundAgentsForSession(
      sessionId,
      tasks.map(childAgentTaskToBackgroundSnapshot),
    );
  } catch (error) {
    s.backgroundAgentsRefreshFailed(
      error instanceof Error ? error.message : String(error),
    );
  }
}
