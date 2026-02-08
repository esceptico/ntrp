import { useState, useEffect, useCallback, useRef } from "react";
import type { Config } from "../types.js";
import { getDashboardOverview, type DashboardOverview } from "../api/client.js";

const POLL_INTERVAL = 2000;

export function useDashboard(config: Config) {
  const [data, setData] = useState<DashboardOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const activeRef = useRef(true);

  const poll = useCallback(async () => {
    try {
      const result = await getDashboardOverview(config);
      if (activeRef.current) {
        setData(result);
        setLoading(false);
      }
    } catch {
      // ignore
    }
  }, [config]);

  useEffect(() => {
    activeRef.current = true;
    poll();
    const interval = setInterval(poll, POLL_INTERVAL);
    return () => {
      activeRef.current = false;
      clearInterval(interval);
    };
  }, [poll]);

  return { data, loading, refresh: poll };
}
