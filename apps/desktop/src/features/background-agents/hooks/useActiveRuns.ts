import { useEffect } from "react";
import { apiWithConfig } from "@/api/core";
import { useStore } from "@/stores";
import { refreshCachedActiveSessionHistories } from "@/actions/history";

const POLL_INTERVAL_MS = 2000;

export interface ActiveRun {
  run_id?: string | null;
  session_id: string;
  status?: string | null;
  backgrounded?: boolean;
}

interface RunsStatus {
  active_runs: ActiveRun[];
}

export function runStatusSnapshots(runs: ActiveRun[]) {
  return runs.map((run) => ({
    runId: run.run_id,
    sessionId: run.session_id,
    status: run.status,
    backgrounded: run.backgrounded,
  }));
}

/** Polls /chat/runs/status so the sidebar can show a streaming indicator
 *  on sessions that have an active run — including ones the user isn't
 *  currently viewing. */
export function useActiveRuns(): void {
  const config = useStore((s) => s.config);
  const connected = useStore((s) => s.connected);
  const syncActiveRuns = useStore((s) => s.syncActiveRuns);

  useEffect(() => {
    if (!connected) return;
    let disposed = false;

    async function tick() {
      try {
        const data = await apiWithConfig<RunsStatus>(config, "/chat/runs/status");
        if (disposed) return;
        const runs = runStatusSnapshots(data.active_runs);
        syncActiveRuns(runs);
        void refreshCachedActiveSessionHistories(runs);
      } catch {
        /* transient — next tick will retry */
      }
    }

    void tick();
    const id = setInterval(tick, POLL_INTERVAL_MS);
    return () => {
      disposed = true;
      clearInterval(id);
    };
  }, [config, connected, syncActiveRuns]);
}
