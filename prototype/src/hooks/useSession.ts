import { useState, useEffect, useRef } from "react";
import type { Config } from "../types.js";
import {
  checkHealth,
  getSession,
  getServerConfig,
  getIndexStatus,
  type ServerConfig,
} from "../api/client.js";
import { INDEX_STATUS_POLL_MS, INDEX_DONE_HIDE_MS } from "../lib/constants.js";

export interface IndexStatus {
  indexing: boolean;
  progress: { total: number; done: number; status: string };
}

export function useSession(config: Config) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sources, setSources] = useState<string[]>([]);
  const [skipApprovals, setSkipApprovals] = useState(false);
  const [serverConnected, setServerConnected] = useState(false);
  const [serverConfig, setServerConfig] = useState<ServerConfig | null>(null);
  const [indexStatus, setIndexStatus] = useState<IndexStatus | null>(null);
  const initRef = useRef(false);

  useEffect(() => {
    if (initRef.current) return;
    initRef.current = true;

    async function init() {
      try {
        const healthy = await checkHealth(config);
        setServerConnected(healthy);

        if (healthy) {
          const [session, configData, idxStatus] = await Promise.all([
            getSession(config),
            getServerConfig(config),
            getIndexStatus(config).catch(() => null),
          ]);

          setSessionId(session.session_id);
          setSources(session.sources);
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

  useEffect(() => {
    if (!serverConnected) return;

    if (indexStatus && !indexStatus.indexing) {
      const timeout = setTimeout(() => {
        setIndexStatus(null);
      }, INDEX_DONE_HIDE_MS);
      return () => clearTimeout(timeout);
    }

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

  const updateSessionInfo = (info: { session_id: string; sources: string[] }) => {
    setSessionId(info.session_id);
    setSources(info.sources);
  };

  const toggleSkipApprovals = () => {
    setSkipApprovals((prev) => !prev);
  };

  const updateServerConfig = (patch: Partial<ServerConfig>) => {
    setServerConfig((prev) => prev && { ...prev, ...patch });
  };

  return {
    sessionId,
    sources,
    skipApprovals,
    serverConnected,
    serverConfig,
    indexStatus,
    refreshIndexStatus,
    updateSessionInfo,
    toggleSkipApprovals,
    updateServerConfig,
  };
}
