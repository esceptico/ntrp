import { useState, useEffect, useRef, useCallback } from "react";
import type { Config } from "../types.js";
import {
  getFacts,
  getObservations,
  getDreams,
  type Fact,
  type Observation,
  type Dream,
} from "../api/client.js";

interface UseMemoryDataResult {
  facts: Fact[];
  observations: Observation[];
  dreams: Dream[];
  loading: boolean;
  error: string | null;
  setFacts: React.Dispatch<React.SetStateAction<Fact[]>>;
  setObservations: React.Dispatch<React.SetStateAction<Observation[]>>;
  setDreams: React.Dispatch<React.SetStateAction<Dream[]>>;
  setError: React.Dispatch<React.SetStateAction<string | null>>;
  reload: () => void;
}

export function useMemoryData(config: Config): UseMemoryDataResult {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [facts, setFacts] = useState<Fact[]>([]);
  const [observations, setObservations] = useState<Observation[]>([]);
  const [dreams, setDreams] = useState<Dream[]>([]);
  const [fetchCount, setFetchCount] = useState(0);

  const fetchIdRef = useRef(0);

  useEffect(() => {
    const id = ++fetchIdRef.current;
    setLoading(true);

    (async () => {
      try {
        const [factsData, obsData, dreamsData] = await Promise.all([
          getFacts(config, 200),
          getObservations(config, 100),
          getDreams(config, 50),
        ]);
        if (fetchIdRef.current !== id) return;
        setFacts(factsData.facts || []);
        setObservations(obsData.observations || []);
        setDreams(dreamsData.dreams || []);
      } catch (e) {
        if (fetchIdRef.current !== id) return;
        setError(`Failed to load: ${e}`);
      } finally {
        if (fetchIdRef.current === id) setLoading(false);
      }
    })();
  }, [config, fetchCount]);

  const reload = useCallback(() => {
    setFetchCount((c) => c + 1);
  }, []);

  return {
    facts,
    observations,
    dreams,
    loading,
    error,
    setFacts,
    setObservations,
    setDreams,
    setError,
    reload,
  };
}
