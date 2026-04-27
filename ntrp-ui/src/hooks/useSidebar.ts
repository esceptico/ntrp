import { useState, useEffect, useCallback, useRef } from "react";
import type { Config } from "../types.js";
import { getContextUsage, getAutomations, listSessions, type Automation, type SessionListItem } from "../api/client.js";
import { getStats, type Stats } from "../api/memory.js";
import type { SidebarSettings } from "./useSettings.js";

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
  memoryStats: Stats | null;
}

const EMPTY: SidebarData = { context: null, nextAutomations: [], sessions: [], memoryStats: null };

export function useSidebar(config: Config, active: boolean, messageCount: number, sessionId: string | null, sidebarSettings?: SidebarSettings) {
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

  const sidebarSettingsRef = useRef(sidebarSettings);
  sidebarSettingsRef.current = sidebarSettings;

  // Full refresh including global data (automations + sessions + memory stats)
  const refresh = useCallback(async () => {
    if (!activeRef.current) return;
    try {
      const sid = sessionIdRef.current ?? undefined;
      const ss = sidebarSettingsRef.current;
      const wantMemory = ss?.memory_stats ?? false;
      const [context, automationsResult, sessionsResult, memoryStats] = await Promise.all([
        getContextUsage(config, sid),
        getAutomations(config),
        listSessions(config).catch(() => ({ sessions: [] })),
        wantMemory ? getStats(config).catch(() => null) : null,
      ]);
      if (!activeRef.current) return;

      const nextAutomations = automationsResult.automations
        .filter(s => s.enabled && (s.next_run_at || s.running_since))
        .sort((a, b) => {
          if (a.running_since && !b.running_since) return -1;
          if (!a.running_since && b.running_since) return 1;
          return new Date(a.next_run_at!).getTime() - new Date(b.next_run_at!).getTime();
        })
        .slice(0, 5);

      setData({ context, nextAutomations, sessions: sessionsResult.sessions, memoryStats });
    } catch {
      // ignore
    }
  }, [config]);

  // Eagerly load sessions + automations on mount
  useEffect(() => {
    const ss = sidebarSettingsRef.current;
    const wantMemory = ss?.memory_stats ?? false;
    Promise.all([
      listSessions(config).catch(() => ({ sessions: [] as SessionListItem[] })),
      getAutomations(config).catch(() => ({ automations: [] as Automation[] })),
      wantMemory ? getStats(config).catch(() => null) : null,
    ]).then(([sessionsResult, automationsResult, memoryStats]) => {
      const nextAutomations = automationsResult.automations
        .filter(s => s.enabled && (s.next_run_at || s.running_since))
        .sort((a, b) => {
          if (a.running_since && !b.running_since) return -1;
          if (!a.running_since && b.running_since) return 1;
          return new Date(a.next_run_at!).getTime() - new Date(b.next_run_at!).getTime();
        })
        .slice(0, 5);
      setData(prev => ({ ...prev, sessions: sessionsResult.sessions, nextAutomations, memoryStats }));
    });
  }, [config]);

  // Refresh session-specific data on tab switch or message changes
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (!active) return;
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    refreshTimerRef.current = setTimeout(refreshSession, 150);
    return () => { if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current); };
  }, [active, sessionId, messageCount, refreshSession]);

  // Fetch memory stats when toggled on
  const wantMemory = sidebarSettings?.memory_stats ?? false;
  useEffect(() => {
    if (!active || !wantMemory) return;
    getStats(config).then(stats => setData(prev => ({ ...prev, memoryStats: stats }))).catch(() => {});
  }, [wantMemory, active, config]);

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
