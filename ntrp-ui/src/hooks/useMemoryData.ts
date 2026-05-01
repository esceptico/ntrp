import { useState, useEffect, useRef, useCallback } from "react";
import type { Config } from "../types.js";
import {
  getFacts,
  getObservations,
  getMemoryPruneDryRun,
  getMemoryEvents,
  getLearningEvents,
  getLearningCandidates,
  getMemoryAccessEvents,
  getMemoryInjectionPolicyPreview,
  getMemoryAudit,
  type Fact,
  type FactFilters,
  type Observation,
  type ObservationFilters,
  type MemoryPruneDryRun,
  type MemoryEvent,
  type LearningEvent,
  type LearningCandidate,
  type MemoryAccessEvent,
  type MemoryInjectionPolicyPreview,
  type MemoryAudit,
} from "../api/client.js";

interface UseMemoryDataResult {
  facts: Fact[];
  factTotal: number;
  observations: Observation[];
  observationTotal: number;
  pruneDryRun: MemoryPruneDryRun | null;
  memoryEvents: MemoryEvent[];
  learningEvents: LearningEvent[];
  learningCandidates: LearningCandidate[];
  memoryAccessEvents: MemoryAccessEvent[];
  memoryAccessFacts: Fact[];
  memoryAccessObservations: Observation[];
  memoryInjectionPolicy: MemoryInjectionPolicyPreview | null;
  memoryAudit: MemoryAudit | null;
  loading: boolean;
  backgroundLoading: boolean;
  error: string | null;
  setFacts: React.Dispatch<React.SetStateAction<Fact[]>>;
  setObservations: React.Dispatch<React.SetStateAction<Observation[]>>;
  setLearningCandidates: React.Dispatch<React.SetStateAction<LearningCandidate[]>>;
  setError: React.Dispatch<React.SetStateAction<string | null>>;
  reload: () => void;
}

export function useMemoryData(config: Config, factFilters?: FactFilters, observationFilters?: ObservationFilters): UseMemoryDataResult {
  const [loading, setLoading] = useState(true);
  const [backgroundLoading, setBackgroundLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [facts, setFacts] = useState<Fact[]>([]);
  const [factTotal, setFactTotal] = useState(0);
  const [observations, setObservations] = useState<Observation[]>([]);
  const [observationTotal, setObservationTotal] = useState(0);
  const [pruneDryRun, setPruneDryRun] = useState<MemoryPruneDryRun | null>(null);
  const [memoryEvents, setMemoryEvents] = useState<MemoryEvent[]>([]);
  const [learningEvents, setLearningEvents] = useState<LearningEvent[]>([]);
  const [learningCandidates, setLearningCandidates] = useState<LearningCandidate[]>([]);
  const [memoryAccessEvents, setMemoryAccessEvents] = useState<MemoryAccessEvent[]>([]);
  const [memoryAccessFacts, setMemoryAccessFacts] = useState<Fact[]>([]);
  const [memoryAccessObservations, setMemoryAccessObservations] = useState<Observation[]>([]);
  const [memoryInjectionPolicy, setMemoryInjectionPolicy] = useState<MemoryInjectionPolicyPreview | null>(null);
  const [memoryAudit, setMemoryAudit] = useState<MemoryAudit | null>(null);
  const [fetchCount, setFetchCount] = useState(0);

  const fetchIdRef = useRef(0);

  useEffect(() => {
    const id = ++fetchIdRef.current;
    let cancelled = false;
    setLoading(true);
    setBackgroundLoading(true);
    setError(null);

    (async () => {
      const isCurrent = () => !cancelled && fetchIdRef.current === id;
      const reportError = (label: string, e: unknown) => {
        if (!isCurrent()) return;
        setError((prev) => prev ?? `${label} failed: ${e}`);
      };

      const fastLoads = [
        getFacts(config, 200, factFilters)
          .then((data) => {
            if (!isCurrent()) return;
            setFacts(data.facts || []);
            setFactTotal(data.total || 0);
          })
          .catch((e: unknown) => reportError("Facts", e)),
        getObservations(config, 100, observationFilters)
          .then((data) => {
            if (!isCurrent()) return;
            setObservations(data.observations || []);
            setObservationTotal(data.total || 0);
          })
          .catch((e: unknown) => reportError("Patterns", e)),
        getMemoryEvents(config, 100)
          .then((data) => {
            if (!isCurrent()) return;
            setMemoryEvents(data.events || []);
          })
          .catch((e: unknown) => reportError("Audit log", e)),
        getLearningEvents(config, 100)
          .then((data) => {
            if (!isCurrent()) return;
            setLearningEvents(data.events || []);
          })
          .catch((e: unknown) => reportError("Learning events", e)),
        getLearningCandidates(config, 100)
          .then((data) => {
            if (!isCurrent()) return;
            setLearningCandidates(data.candidates || []);
          })
          .catch((e: unknown) => reportError("Learning candidates", e)),
        getMemoryAccessEvents(config, 100)
          .then((data) => {
            if (!isCurrent()) return;
            setMemoryAccessEvents(data.events || []);
            setMemoryAccessFacts(data.facts || []);
            setMemoryAccessObservations(data.observations || []);
          })
          .catch((e: unknown) => reportError("Sent memory", e)),
      ];

      await Promise.allSettled(fastLoads);
      if (!isCurrent()) return;
      setLoading(false);

      const slowLoads = [
        getMemoryPruneDryRun(config)
          .then((data) => {
            if (!isCurrent()) return;
            setPruneDryRun(data);
          })
          .catch((e: unknown) => reportError("Cleanup preview", e)),
        getMemoryInjectionPolicyPreview(config, 100)
          .then((data) => {
            if (!isCurrent()) return;
            setMemoryInjectionPolicy(data);
          })
          .catch((e: unknown) => reportError("Sent-memory policy", e)),
        getMemoryAudit(config)
          .then((data) => {
            if (!isCurrent()) return;
            setMemoryAudit(data);
          })
          .catch((e: unknown) => reportError("Memory health", e)),
      ];

      await Promise.allSettled(slowLoads);
      if (isCurrent()) setBackgroundLoading(false);
    })().catch((e: unknown) => {
      if (fetchIdRef.current !== id) return;
      setError(`Failed to load: ${e}`);
      setLoading(false);
      setBackgroundLoading(false);
    });

    return () => {
      cancelled = true;
    };
  }, [config, fetchCount, factFilters, observationFilters]);

  const reload = useCallback(() => {
    setFetchCount((c) => c + 1);
  }, []);

  return {
    facts,
    factTotal,
    observations,
    observationTotal,
    pruneDryRun,
    memoryEvents,
    learningEvents,
    learningCandidates,
    memoryAccessEvents,
    memoryAccessFacts,
    memoryAccessObservations,
    memoryInjectionPolicy,
    memoryAudit,
    loading,
    backgroundLoading,
    error,
    setFacts,
    setObservations,
    setLearningCandidates,
    setError,
    reload,
  };
}
