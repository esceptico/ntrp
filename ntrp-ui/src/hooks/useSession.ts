import { useState, useEffect, useRef, useCallback } from "react";
import type { Config } from "../types.js";
import {
  checkHealth,
  getSession,
  getServerConfig,
  getIndexStatus,
  getHistory,
  createSession,
  type ServerConfig,
  type HistoryMessage,
} from "../api/client.js";
import { INDEX_STATUS_POLL_MS, INDEX_DONE_HIDE_MS } from "../lib/constants.js";

interface IndexStatus {
  indexing: boolean;
  progress: { total: number; done: number; status: string };
  reembedding?: boolean;
  reembed_progress?: { total: number; done: number } | null;
}

export function useSession(config: Config) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessionName, setSessionName] = useState<string | null>(null);
  const [sources, setSources] = useState<string[]>([]);
  const [skipApprovals, setSkipApprovals] = useState(false);
  const [serverConnected, setServerConnected] = useState(false);
  const [serverConfig, setServerConfig] = useState<ServerConfig | null>(null);
  const [indexStatus, setIndexStatus] = useState<IndexStatus | null>(null);
  const [history, setHistory] = useState<HistoryMessage[]>([]);
  const initRef = useRef(false);

  useEffect(() => {
    if (initRef.current) return;
    initRef.current = true;

    async function waitForServer(maxAttempts = 30, intervalMs = 1000): Promise<boolean> {
      for (let i = 0; i < maxAttempts; i++) {
        if (await checkHealth(config)) return true;
        await new Promise((r) => setTimeout(r, intervalMs));
      }
      return false;
    }

    async function init() {
      try {
        const healthy = await waitForServer();
        setServerConnected(healthy);

        if (healthy) {
          const [session, configData, idxStatus, historyData] = await Promise.all([
            getSession(config),
            getServerConfig(config),
            getIndexStatus(config).catch(() => null),
            getHistory(config).catch(() => ({ messages: [] })),
          ]);

          setSessionId(session.session_id);
          setSessionName(session.name ?? null);
          setSources(session.sources);
          setServerConfig(configData);
          setHistory(historyData.messages);

          if (idxStatus?.indexing || idxStatus?.reembedding) {
            setIndexStatus(idxStatus);
          }
        }
      } catch {
        setServerConnected(false);
      }
    }
    init();
  }, [config]);

  useEffect(() => {
    if (!serverConnected) return;

    const isActive = indexStatus?.indexing || indexStatus?.reembedding;

    if (indexStatus && !isActive) {
      const timeout = setTimeout(() => {
        setIndexStatus(null);
      }, INDEX_DONE_HIDE_MS);
      return () => clearTimeout(timeout);
    }

    if (!isActive) return;

    const interval = setInterval(async () => {
      try {
        const status = await getIndexStatus(config);
        setIndexStatus(status);
      } catch {
        // Ignore errors
      }
    }, INDEX_STATUS_POLL_MS);

    return () => clearInterval(interval);
  }, [serverConnected, indexStatus, config]);

  const refreshIndexStatus = async () => {
    try {
      const status = await getIndexStatus(config);
      setIndexStatus(status);
    } catch {
      // Ignore errors
    }
  };

  const updateSessionInfo = (info: { session_id: string; sources?: string[]; session_name?: string }) => {
    setSessionId(info.session_id);
    if (info.sources !== undefined) {
      setSources(info.sources);
    }
    if (info.session_name !== undefined) {
      setSessionName(info.session_name || null);
    }
  };

  const toggleSkipApprovals = () => {
    setSkipApprovals((prev) => !prev);
  };

  const updateServerConfig = (patch: Partial<ServerConfig>) => {
    setServerConfig((prev) => prev && { ...prev, ...patch });
  };

  const switchSession = useCallback(async (targetSessionId: string): Promise<{ history: HistoryMessage[] } | null> => {
    try {
      const [session, historyData] = await Promise.all([
        getSession(config, targetSessionId),
        getHistory(config, targetSessionId).catch(() => ({ messages: [] })),
      ]);
      setSessionId(session.session_id);
      setSessionName(session.name ?? null);
      setSources(session.sources);
      setHistory(historyData.messages);
      return { history: historyData.messages };
    } catch {
      return null;
    }
  }, [config]);

  const createNewSession = useCallback(async (name?: string): Promise<string | null> => {
    try {
      const result = await createSession(config, name);
      setSessionId(result.session_id);
      setSessionName(result.name ?? null);
      setSources([]);
      setHistory([]);
      return result.session_id;
    } catch {
      return null;
    }
  }, [config]);

  return {
    sessionId,
    sessionName,
    sources,
    skipApprovals,
    serverConnected,
    serverConfig,
    indexStatus,
    history,
    refreshIndexStatus,
    updateSessionInfo,
    toggleSkipApprovals,
    updateServerConfig,
    switchSession,
    createNewSession,
  };
}
