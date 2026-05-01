import { useState, useEffect, useRef, useCallback } from "react";
import type { Config } from "../types.js";
import {
  getFacts,
  getMemoryProfile,
  getObservations,
  getMemoryPruneDryRun,
  getMemoryEvents,
  getMemoryAudit,
  type Fact,
  type FactFilters,
  type Observation,
  type ObservationFilters,
  type MemoryPruneDryRun,
  type MemoryEvent,
  type MemoryAudit,
} from "../api/client.js";

interface UseMemoryDataResult {
  facts: Fact[];
  factTotal: number;
  profileFacts: Fact[];
  observations: Observation[];
  observationTotal: number;
  pruneDryRun: MemoryPruneDryRun | null;
  memoryEvents: MemoryEvent[];
  memoryAudit: MemoryAudit | null;
  loading: boolean;
  error: string | null;
  setFacts: React.Dispatch<React.SetStateAction<Fact[]>>;
  setObservations: React.Dispatch<React.SetStateAction<Observation[]>>;
  setError: React.Dispatch<React.SetStateAction<string | null>>;
  reload: () => void;
}

export function useMemoryData(config: Config, factFilters?: FactFilters, observationFilters?: ObservationFilters): UseMemoryDataResult {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [facts, setFacts] = useState<Fact[]>([]);
  const [factTotal, setFactTotal] = useState(0);
  const [profileFacts, setProfileFacts] = useState<Fact[]>([]);
  const [observations, setObservations] = useState<Observation[]>([]);
  const [observationTotal, setObservationTotal] = useState(0);
  const [pruneDryRun, setPruneDryRun] = useState<MemoryPruneDryRun | null>(null);
  const [memoryEvents, setMemoryEvents] = useState<MemoryEvent[]>([]);
  const [memoryAudit, setMemoryAudit] = useState<MemoryAudit | null>(null);
  const [fetchCount, setFetchCount] = useState(0);

  const fetchIdRef = useRef(0);

  useEffect(() => {
    const id = ++fetchIdRef.current;
    setLoading(true);

    (async () => {
      try {
        const [factsData, profileData, obsData, pruneData, eventsData, auditData] = await Promise.all([
          getFacts(config, 200, factFilters),
          getMemoryProfile(config, 20),
          getObservations(config, 100, observationFilters),
          getMemoryPruneDryRun(config),
          getMemoryEvents(config, 100),
          getMemoryAudit(config),
        ]);
        if (fetchIdRef.current !== id) return;
        setFacts(factsData.facts || []);
        setFactTotal(factsData.total || 0);
        setProfileFacts(profileData.facts || []);
        setObservations(obsData.observations || []);
        setObservationTotal(obsData.total || 0);
        setPruneDryRun(pruneData);
        setMemoryEvents(eventsData.events || []);
        setMemoryAudit(auditData);
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
    profileFacts,
    observations,
    observationTotal,
    pruneDryRun,
    memoryEvents,
    memoryAudit,
    loading,
    error,
    setFacts,
    setObservations,
    setError,
    reload,
  };
}
