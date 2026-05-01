import { useState, useEffect, useRef, useCallback } from "react";
import type { Config } from "../types.js";
import {
  getFacts,
  getMemoryProfile,
  getMemoryProfilePolicyPreview,
  getObservations,
  getMemoryPruneDryRun,
  getMemoryEvents,
  getMemoryAccessEvents,
  getMemoryInjectionPolicyPreview,
  getMemoryAudit,
  type Fact,
  type FactFilters,
  type Observation,
  type ObservationFilters,
  type MemoryPruneDryRun,
  type MemoryEvent,
  type MemoryAccessEvent,
  type MemoryInjectionPolicyPreview,
  type MemoryProfilePolicyPreview,
  type MemoryAudit,
} from "../api/client.js";

interface UseMemoryDataResult {
  facts: Fact[];
  factTotal: number;
  profileFacts: Fact[];
  memoryProfilePolicy: MemoryProfilePolicyPreview | null;
  observations: Observation[];
  observationTotal: number;
  pruneDryRun: MemoryPruneDryRun | null;
  memoryEvents: MemoryEvent[];
  memoryAccessEvents: MemoryAccessEvent[];
  memoryInjectionPolicy: MemoryInjectionPolicyPreview | null;
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
  const [memoryProfilePolicy, setMemoryProfilePolicy] = useState<MemoryProfilePolicyPreview | null>(null);
  const [observations, setObservations] = useState<Observation[]>([]);
  const [observationTotal, setObservationTotal] = useState(0);
  const [pruneDryRun, setPruneDryRun] = useState<MemoryPruneDryRun | null>(null);
  const [memoryEvents, setMemoryEvents] = useState<MemoryEvent[]>([]);
  const [memoryAccessEvents, setMemoryAccessEvents] = useState<MemoryAccessEvent[]>([]);
  const [memoryInjectionPolicy, setMemoryInjectionPolicy] = useState<MemoryInjectionPolicyPreview | null>(null);
  const [memoryAudit, setMemoryAudit] = useState<MemoryAudit | null>(null);
  const [fetchCount, setFetchCount] = useState(0);

  const fetchIdRef = useRef(0);

  useEffect(() => {
    const id = ++fetchIdRef.current;
    setLoading(true);

    (async () => {
      try {
        const [
          factsData,
          profileData,
          profilePolicyData,
          obsData,
          pruneData,
          eventsData,
          accessData,
          policyData,
          auditData,
        ] = await Promise.all([
          getFacts(config, 200, factFilters),
          getMemoryProfile(config, 20),
          getMemoryProfilePolicyPreview(config, 100),
          getObservations(config, 100, observationFilters),
          getMemoryPruneDryRun(config),
          getMemoryEvents(config, 100),
          getMemoryAccessEvents(config, 100),
          getMemoryInjectionPolicyPreview(config, 100),
          getMemoryAudit(config),
        ]);
        if (fetchIdRef.current !== id) return;
        setFacts(factsData.facts || []);
        setFactTotal(factsData.total || 0);
        setProfileFacts(profileData.facts || []);
        setMemoryProfilePolicy(profilePolicyData);
        setObservations(obsData.observations || []);
        setObservationTotal(obsData.total || 0);
        setPruneDryRun(pruneData);
        setMemoryEvents(eventsData.events || []);
        setMemoryAccessEvents(accessData.events || []);
        setMemoryInjectionPolicy(policyData);
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
    memoryProfilePolicy,
    observations,
    observationTotal,
    pruneDryRun,
    memoryEvents,
    memoryAccessEvents,
    memoryInjectionPolicy,
    memoryAudit,
    loading,
    error,
    setFacts,
    setObservations,
    setError,
    reload,
  };
}
