import { useState, useEffect, useCallback, useRef } from "react";
import type { Config } from "../types.js";
import { getContextUsage, getAutomations, listSessions, type Automation, type SessionListItem } from "../api/client.js";

const POLL_INTERVAL = 60_000;

export interface SidebarData {
  context: {
    model: string;
    total: number | null;
    limit: number;
    message_count: number;
    tool_count: number;
  } | null;
  nextAutomations: Automation[];
  sessions: SessionListItem[];
}

const EMPTY: SidebarData = { context: null, nextAutomations: [], sessions: [] };

export function useSidebar(config: Config, active: boolean, messageCount: number, sessionId: string | null) {
  const [data, setData] = useState<SidebarData>(EMPTY);
  const activeRef = useRef(true);
  const sessionIdRef = useRef(sessionId);
  sessionIdRef.current = sessionId;

  // Session-specific data only (context)
  const refreshSession = useCallback(async () => {
    if (!activeRef.current) return;
    try {
      const sid = sessionIdRef.current ?? undefined;
      const context = await getContextUsage(config, sid);
      if (!activeRef.current) return;
      setData(prev => ({ ...prev, context }));
    } catch {
      // ignore
    }
  }, [config]);

  // Full refresh including global data (automations + sessions)
  const refresh = useCallback(async () => {
    if (!activeRef.current) return;
    try {
      const sid = sessionIdRef.current ?? undefined;
      const [context, automationsResult, sessionsResult] = await Promise.all([
        getContextUsage(config, sid),
        getAutomations(config),
        listSessions(config).catch(() => ({ sessions: [] })),
      ]);
      if (!activeRef.current) return;

      const nextAutomations = automationsResult.automations
        .filter(s => s.enabled && s.next_run_at)
        .sort((a, b) => new Date(a.next_run_at!).getTime() - new Date(b.next_run_at!).getTime())
        .slice(0, 3);

      setData({ context, nextAutomations, sessions: sessionsResult.sessions });
    } catch {
      // ignore
    }
  }, [config]);

  // Eagerly load sessions on mount so cycleSession always has data
  useEffect(() => {
    listSessions(config).then(r => {
      setData(prev => ({ ...prev, sessions: r.sessions }));
    }).catch(() => {});
  }, [config]);

  // Refresh session-specific data on tab switch or message changes
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (!active) return;
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    refreshTimerRef.current = setTimeout(refreshSession, 150);
    return () => { if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current); };
  }, [active, sessionId, messageCount, refreshSession]);

  // Fallback poll for all data including global
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
