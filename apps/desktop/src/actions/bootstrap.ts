import { apiWithConfig, checkHealth, loadInitialConfig, type SessionListItem } from "../api";
import { getState } from "../store";
import { loadHistory } from "./history";
import { fetchSkills } from "./skills";
import { fetchServerConfig } from "./server";

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
