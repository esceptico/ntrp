import { useState, useEffect, useCallback, useRef } from "react";
import type { Config } from "../types.js";
import { getStats, getContextUsage, getSchedules, listSessions, type Stats, type Schedule, type SessionListItem } from "../api/client.js";

const POLL_INTERVAL = 60_000;

export interface SidebarData {
  stats: Stats | null;
  context: {
    model: string;
    total: number | null;
    limit: number;
    message_count: number;
    tool_count: number;
  } | null;
  nextSchedules: Schedule[];
  sessions: SessionListItem[];
}

const EMPTY: SidebarData = { stats: null, context: null, nextSchedules: [], sessions: [] };

export function useSidebar(config: Config, active: boolean, messageCount: number, sessionId: string | null) {
  const [data, setData] = useState<SidebarData>(EMPTY);
  const activeRef = useRef(true);
  const sessionIdRef = useRef(sessionId);
  sessionIdRef.current = sessionId;

  const refresh = useCallback(async () => {
    if (!activeRef.current) return;
    try {
      const sid = sessionIdRef.current ?? undefined;
      const [stats, context, schedulesResult, sessionsResult] = await Promise.all([
        getStats(config),
        getContextUsage(config, sid),
        getSchedules(config),
        listSessions(config).catch(() => ({ sessions: [] })),
      ]);
      if (!activeRef.current) return;

      const nextSchedules = schedulesResult.schedules
        .filter(s => s.enabled && s.next_run_at)
        .sort((a, b) => new Date(a.next_run_at!).getTime() - new Date(b.next_run_at!).getTime())
        .slice(0, 3);

      setData({ stats, context, nextSchedules, sessions: sessionsResult.sessions });
    } catch {
      // ignore
    }
  }, [config]);

  // Refresh on session or message changes
  useEffect(() => {
    if (active) refresh();
  }, [active, sessionId, messageCount, refresh]);

  // Fallback poll for external changes (schedules, etc.)
  useEffect(() => {
    if (!active) return;
    activeRef.current = true;
    const interval = setInterval(refresh, POLL_INTERVAL);
    return () => {
      activeRef.current = false;
      clearInterval(interval);
    };
  }, [refresh, active]);

  return { data, refresh };
}
