import { useState, useEffect, useRef, useCallback } from "react";
import type { Config } from "../types.js";
import {
  getFacts,
  getObservations,
  getDreams,
  getMemoryPruneDryRun,
  type Fact,
  type FactFilters,
  type Observation,
  type ObservationFilters,
  type Dream,
  type MemoryPruneDryRun,
} from "../api/client.js";

interface UseMemoryDataResult {
  facts: Fact[];
  factTotal: number;
  observations: Observation[];
  observationTotal: number;
  dreams: Dream[];
  pruneDryRun: MemoryPruneDryRun | null;
  loading: boolean;
  error: string | null;
  setFacts: React.Dispatch<React.SetStateAction<Fact[]>>;
  setObservations: React.Dispatch<React.SetStateAction<Observation[]>>;
  setDreams: React.Dispatch<React.SetStateAction<Dream[]>>;
  setError: React.Dispatch<React.SetStateAction<string | null>>;
  reload: () => void;
}

export function useMemoryData(config: Config, factFilters?: FactFilters, observationFilters?: ObservationFilters): UseMemoryDataResult {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [facts, setFacts] = useState<Fact[]>([]);
  const [factTotal, setFactTotal] = useState(0);
  const [observations, setObservations] = useState<Observation[]>([]);
  const [observationTotal, setObservationTotal] = useState(0);
  const [dreams, setDreams] = useState<Dream[]>([]);
  const [pruneDryRun, setPruneDryRun] = useState<MemoryPruneDryRun | null>(null);
  const [fetchCount, setFetchCount] = useState(0);

  const fetchIdRef = useRef(0);

  useEffect(() => {
    const id = ++fetchIdRef.current;
    setLoading(true);

    (async () => {
      try {
        const [factsData, obsData, dreamsData, pruneData] = await Promise.all([
          getFacts(config, 200, factFilters),
          getObservations(config, 100, observationFilters),
          getDreams(config, 50),
          getMemoryPruneDryRun(config),
        ]);
        if (fetchIdRef.current !== id) return;
        setFacts(factsData.facts || []);
        setFactTotal(factsData.total || 0);
        setObservations(obsData.observations || []);
        setObservationTotal(obsData.total || 0);
        setDreams(dreamsData.dreams || []);
        setPruneDryRun(pruneData);
      } catch (e) {
        if (fetchIdRef.current !== id) return;
        setError(`Failed to load: ${e}`);
      } finally {
        if (fetchIdRef.current === id) setLoading(false);
      }
    })();
  }, [config, fetchCount, factFilters, observationFilters]);

  const reload = useCallback(() => {
    setFetchCount((c) => c + 1);
  }, []);

  return {
    facts,
    factTotal,
    observations,
    observationTotal,
    dreams,
    pruneDryRun,
    loading,
    error,
    setFacts,
    setObservations,
    setDreams,
    setError,
    reload,
  };
}
