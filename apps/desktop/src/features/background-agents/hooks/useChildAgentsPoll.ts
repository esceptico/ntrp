import { useEffect } from "react";
import { refreshChildAgents } from "@/actions/childAgents";

export function useChildAgentsPoll(sessionId: string | null): void {
  // Live BackgroundTaskEvents already keep the roster current for the session
  // being viewed; this poll is the fallback for the cases events don't cover
  // (agents spawned in the parent while a child is open, terminal status missed
  // while disconnected). Reconnect resync lives in reloadAllCollections.
  useEffect(() => {
    if (!sessionId) return;
    const tick = () => {
      if (document.visibilityState === "visible") void refreshChildAgents(sessionId);
    };
    void refreshChildAgents(sessionId);
    const id = window.setInterval(tick, 5000);
    document.addEventListener("visibilitychange", tick);
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [sessionId]);
}
