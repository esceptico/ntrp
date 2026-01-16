/**
 * Hook for managing server session and initialization.
 */
import { useState, useEffect, useRef } from "react";
import type { Config } from "../types.js";
import {
  checkHealth,
  getSession,
  getStats,
  getServerConfig,
  getIndexStatus,
  type Stats,
  type ServerConfig,
} from "../api/client.js";
import { INDEX_STATUS_POLL_MS, INDEX_DONE_HIDE_MS } from "../lib/constants.js";

export interface IndexStatus {
  indexing: boolean;
  progress: { total: number; done: number; status: string };
}

export interface SessionState {
  sessionId: string | null;
  sources: string[];
  yolo: boolean;
  serverConnected: boolean;
  stats: Stats | null;
  serverConfig: ServerConfig | null;
  indexStatus: IndexStatus | null;
}

export function useSession(config: Config) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sources, setSources] = useState<string[]>([]);
  const [yolo, setYolo] = useState(false);
  const [serverConnected, setServerConnected] = useState(false);
  const [stats, setStats] = useState<Stats | null>(null);
  const [serverConfig, setServerConfig] = useState<ServerConfig | null>(null);
  const [indexStatus, setIndexStatus] = useState<IndexStatus | null>(null);
  const initRef = useRef(false);

  // Initial server check and session load
  useEffect(() => {
    if (initRef.current) return;
    initRef.current = true;

    async function init() {
      try {
        const healthy = await checkHealth(config);
        setServerConnected(healthy);

        if (healthy) {
          const [session, statsData, configData, idxStatus] = await Promise.all([
            getSession(config),
            getStats(config),
            getServerConfig(config),
            getIndexStatus(config).catch(() => null),
          ]);

          setSessionId(session.session_id);
          setSources(session.sources);
          setStats(statsData);
          setServerConfig(configData);

          if (idxStatus?.indexing) {
            setIndexStatus(idxStatus);
          }
        }
      } catch {
        setServerConnected(false);
      }
    }
    init();
  }, [config]);

  // Poll index status while indexing
  useEffect(() => {
    if (!serverConnected) return;

    // Clear status after indexing completes
    if (indexStatus && !indexStatus.indexing) {
      const timeout = setTimeout(() => {
        setIndexStatus(null);
      }, INDEX_DONE_HIDE_MS);
      return () => clearTimeout(timeout);
    }

    // Poll while indexing
    if (!indexStatus?.indexing) return;

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

  return {
    sessionId,
    setSessionId,
    sources,
    setSources,
    yolo,
    setYolo,
    serverConnected,
    stats,
    serverConfig,
    setServerConfig,
    indexStatus,
    refreshIndexStatus,
  };
}
