import { useEffect, useRef, useState } from "react";
import type { KnowledgeActivationUsageEvent, KnowledgeFactConsolidationProposal, KnowledgeFactConsolidationResult, KnowledgeObject, KnowledgeSourceTraceResult, KnowledgeUsageObjectSummary, KnowledgeWorkflowCluster, KnowledgeWorkflowClusterResult } from "../../api";
import {
  commitKnowledgeFactConsolidationApi,
  createKnowledgeSkillPromotionApi,
  getKnowledgeFactConsolidationApi,
  getKnowledgeObjectSourcesApi,
  getKnowledgeWorkflowClustersApi,
  listKnowledgeObjectsApi,
  listKnowledgeActivationUsageEventsApi,
  listKnowledgeUsageSummaryApi,
  proposeKnowledgeSkillPromotionsApi,
  publishKnowledgeArtifactApi,
  recordKnowledgeUsageEventOutcomeApi,
  reviewKnowledgeWorkflowClusterApi,
  updateKnowledgeObjectApi,
} from "../../api";
import { useStore } from "../../store";
import { formatRelativePast } from "../../lib/format";
import {
  KNOWLEDGE_REVIEW_TYPES,
  SKILL_ACTIVATION_SUBTYPE_FILTERS,
  isSkillPromotionCandidate,
  reviewActionLabel,
  reviewKind,
  reviewOutcomeHint,
  shouldReviewKnowledgeObject,
  skillActivationSubtypeKey,
  skillActivationSubtypeLabel,
  type SkillActivationSubtypeKey,
} from "../../lib/knowledgeViews";
import { ErrorPill, GhostBtn, Pill } from "./shared";
import { ScrollBlurTop } from "../ScrollBlur";

const REVIEW_PAGE_SIZE = 250;


function detailText(details: Record<string, unknown>, key: string) {
  const value = details[key];
  if (typeof value === "string") return value.trim() ? value.trim() : null;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return null;
}

function topCounterLabel(counter: Record<string, number>, fallback = "none") {
  const entries = Object.entries(counter).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) return fallback;
  return entries.slice(0, 2).map(([key, value]) => `${key}: ${value}`).join(" · ");
}


function SkillActivationList({ events }: { events: KnowledgeActivationUsageEvent[] | null }) {
  const [subtypeFilter, setSubtypeFilter] = useState<SkillActivationSubtypeKey>("all");

  if (!events || events.length === 0) return null;

  const subtypeCounts = events.reduce<Record<SkillActivationSubtypeKey, number>>(
    (counts, event) => {
      counts.all += 1;
      counts[skillActivationSubtypeKey(event)] += 1;
      return counts;
    },
    {
      all: 0,
      explicit: 0,
      chat_auto: 0,
      operator_auto: 0,
      background_auto: 0,
      research_auto: 0,
      other_auto: 0,
      other: 0,
    },
  );
  const visibleFilters = SKILL_ACTIVATION_SUBTYPE_FILTERS.filter(
    (filter) => filter.key === "all" || filter.key === subtypeFilter || subtypeCounts[filter.key] > 0,
  );
  const filteredEvents =
    subtypeFilter === "all" ? events : events.filter((event) => skillActivationSubtypeKey(event) === subtypeFilter);

  return (
    <div className="mt-3 border-t border-line-soft pt-3">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs font-semibold uppercase tracking-wide text-faint">Skill activations</div>
        <div className="flex flex-wrap gap-1.5" aria-label="Skill activation subtype filters">
          {visibleFilters.map((filter) => (
            <button
              key={filter.key}
              type="button"
              onClick={() => setSubtypeFilter(filter.key)}
              className={`rounded-full border px-2 py-0.5 text-[11px] transition ${
                subtypeFilter === filter.key
                  ? "border-accent/70 bg-accent/10 text-ink"
                  : "border-line-soft bg-bg text-faint hover:text-ink-soft"
              }`}
            >
              {filter.label} <span className="text-faint">{subtypeCounts[filter.key]}</span>
            </button>
          ))}
        </div>
      </div>
      {filteredEvents.length === 0 ? (
        <div className="rounded-[8px] border border-line-soft bg-bg px-3 py-2 text-xs text-faint">
          No skill activations for this subtype.
        </div>
      ) : (
        <ul className="m-0 grid list-none gap-2 p-0">
          {filteredEvents.map((event) => {
            const skillName = detailText(event.details, "skill_name") ?? "unknown skill";
            const skillPath = detailText(event.details, "skill_path");
            const runId = detailText(event.details, "run_id");
            const sessionId = detailText(event.details, "session_id");
            const toolId = detailText(event.details, "tool_id");
            const surface = detailText(event.details, "surface");
            const location = detailText(event.details, "skill_location");
            const skillSource = detailText(event.details, "skill_source");
            const skillArgs = detailText(event.details, "skill_args");
            const activationSurface = detailText(event.details, "activation_surface");
            const triggeringUsageEventId = detailText(event.details, "triggering_usage_event_id");
            const triggeringMemoryObjectId = detailText(event.details, "triggering_memory_object_id");
            const subtypeLabel = skillActivationSubtypeLabel(event);
            return (
              <li key={event.id} className="rounded-[8px] border border-line-soft bg-bg px-3 py-2 text-xs text-faint">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="font-medium text-ink-soft">{skillName}</div>
                  <div className="flex flex-wrap gap-1.5">
                    <Pill>{subtypeLabel}</Pill>
                    {surface && <Pill>{surface}</Pill>}
                    {location && <Pill>{location}</Pill>}
                    <Pill>{event.policy_version}</Pill>
                    <Pill>{formatRelativePast(event.created_at)}</Pill>
                  </div>
                </div>
                <div className="mt-1">
                  {skillPath && <span>{skillPath}</span>}
                  {skillSource && <span> · source {skillSource}</span>}
                  {activationSurface && <span> · surface {activationSurface}</span>}
                  {triggeringUsageEventId && <span> · triggered by usage event {triggeringUsageEventId}</span>}
                  {triggeringMemoryObjectId && <span> · memory {triggeringMemoryObjectId}</span>}
                  {sessionId && <span> · session {sessionId}</span>}
                  {runId && <span> · run {runId}</span>}
                  {toolId && <span> · tool {toolId}</span>}
                  {skillArgs && <span> · args “{skillArgs.length > 140 ? `${skillArgs.slice(0, 140)}…` : skillArgs}”</span>}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}


function ReviewEvidence({ item }: { item: KnowledgeObject }) {
  const confidence = typeof item.metadata.confidence === "number" ? `${Math.round(item.metadata.confidence * 100)}% confidence` : null;
  const kind = typeof item.metadata.kind === "string" ? item.metadata.kind : null;
  const sourceQuote = typeof item.metadata.source_quote === "string" ? item.metadata.source_quote : null;
  const skillName = typeof item.metadata.skill_name === "string" ? item.metadata.skill_name : null;
  const skillDescription = typeof item.metadata.skill_description === "string" ? item.metadata.skill_description : null;
  const skillBody = typeof item.metadata.skill_body === "string" ? item.metadata.skill_body : null;

  if (!confidence && !kind && !sourceQuote && !skillName && !skillDescription && !skillBody) return null;

  return (
    <div className="mt-2 rounded-md border border-line-soft bg-bg-main px-2 py-2 text-xs leading-snug text-faint">
      <div className="flex flex-wrap gap-1.5">
        {kind && <Pill>{kind}</Pill>}
        {confidence && <Pill>{confidence}</Pill>}
        {skillName && <Pill>{skillName}</Pill>}
      </div>
      {skillDescription && <p className="m-0 mt-2 whitespace-pre-wrap text-ink-soft">{skillDescription}</p>}
      {skillBody && <pre className="m-0 mt-2 max-h-72 overflow-y-auto whitespace-pre-wrap rounded-md border border-line-soft bg-bg-elevated px-2 py-2 text-xs text-ink-soft">{skillBody}</pre>}
      {sourceQuote && <p className="m-0 mt-2 whitespace-pre-wrap text-ink-soft">“{sourceQuote}”</p>}
    </div>
  );
}


function WorkflowReviewMarkerDetails({ cluster }: { cluster: KnowledgeWorkflowCluster }) {
  const metadata = cluster.metadata ?? {};
  const status = typeof metadata.workflow_review_status === "string" ? metadata.workflow_review_status : null;
  const reason = typeof metadata.workflow_review_reason === "string" && metadata.workflow_review_reason.trim() ? metadata.workflow_review_reason.trim() : null;
  const reviewedAt = typeof metadata.workflow_reviewed_at === "string" ? metadata.workflow_reviewed_at : null;
  const reviewObjectId = typeof metadata.workflow_review_object_id === "number" ? metadata.workflow_review_object_id : null;
  if (!status && !reason && !reviewedAt && reviewObjectId == null) return null;

  return (
    <div className="mt-2 rounded-md border border-line-soft bg-bg-main px-2 py-2 text-[11px] leading-snug text-faint">
      <div className="flex flex-wrap gap-1.5">
        {status && <Pill>review {status}</Pill>}
        {reviewObjectId != null && <Pill>marker:{reviewObjectId}</Pill>}
        {reviewedAt && <Pill>reviewed {new Date(reviewedAt).toLocaleDateString()}</Pill>}
      </div>
      {reason && <p className="m-0 mt-2 whitespace-pre-wrap text-ink-soft">Reason: {reason}</p>}
    </div>
  );
}

export function KnowledgeReviewPane() {
  const config = useStore((s) => s.config);
  const [items, setItems] = useState<KnowledgeObject[] | null>(null);
  const [consolidation, setConsolidation] = useState<KnowledgeFactConsolidationResult | null>(null);
  const [workflowClusters, setWorkflowClusters] = useState<KnowledgeWorkflowClusterResult | null>(null);
  const [usageSummary, setUsageSummary] = useState<KnowledgeUsageObjectSummary[] | null>(null);
  const [skillActivations, setSkillActivations] = useState<KnowledgeActivationUsageEvent[] | null>(null);
  const [usageError, setUsageError] = useState<string | null>(null);
  const [sources, setSources] = useState<Record<number, KnowledgeSourceTraceResult>>({});
  const [sourceErrors, setSourceErrors] = useState<Record<number, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [sourceBusyId, setSourceBusyId] = useState<number | null>(null);
  const [usageBusyKey, setUsageBusyKey] = useState<string | null>(null);
  const [workflowBusy, setWorkflowBusy] = useState(false);
  const [workflowReviewBusyKey, setWorkflowReviewBusyKey] = useState<string | null>(null);
  const [workflowMessage, setWorkflowMessage] = useState<string | null>(null);
  const loadGenerationRef = useRef(0);
  const sourceGenerationRef = useRef(0);
  const consolidationGenerationRef = useRef(0);
  const workflowGenerationRef = useRef(0);
  const usageGenerationRef = useRef(0);

  async function load(options: { refreshSnapshots?: boolean } = {}) {
    const generation = ++loadGenerationRef.current;
    const consolidationGeneration = ++consolidationGenerationRef.current;
    const workflowGeneration = ++workflowGenerationRef.current;
    const usageGeneration = ++usageGenerationRef.current;
    sourceGenerationRef.current += 1;
    setSourceBusyId(null);
    setConsolidation(null);
    setWorkflowClusters(null);
    setUsageSummary(null);
    setSkillActivations(null);
    setUsageError(null);
    setError(null);
    try {
      const results = await Promise.all(
        KNOWLEDGE_REVIEW_TYPES.map((type) =>
          listKnowledgeObjectsApi(config, { object_type: type, status: "draft", limit: REVIEW_PAGE_SIZE }),
        ),
      );
      if (generation !== loadGenerationRef.current) return;
      const nextItems = results
        .flatMap((result) => result.objects)
        .filter(shouldReviewKnowledgeObject)
        .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());
      const nextIds = new Set(nextItems.map((item) => item.id));
      setItems(nextItems);
      setSources((current) => Object.fromEntries(Object.entries(current).filter(([id]) => nextIds.has(Number(id)))));
      setSourceErrors((current) => Object.fromEntries(Object.entries(current).filter(([id]) => nextIds.has(Number(id)))));

      void getKnowledgeFactConsolidationApi(config, {
        limit: 1_000,
        min_confidence: 0.86,
        max_proposals: 25,
        refresh: options.refreshSnapshots ?? false,
      })
        .then((nextConsolidation) => {
          if (generation === loadGenerationRef.current && consolidationGeneration === consolidationGenerationRef.current) {
            setConsolidation(nextConsolidation);
          }
        })
        .catch((e) => {
          if (generation === loadGenerationRef.current && consolidationGeneration === consolidationGenerationRef.current) {
            setError(e instanceof Error ? e.message : String(e));
          }
        });

      void getKnowledgeWorkflowClustersApi(config, {
        limit: 1_000,
        min_successes: 3,
        refresh: options.refreshSnapshots ?? false,
      })
        .then((nextClusters) => {
          if (generation === loadGenerationRef.current && workflowGeneration === workflowGenerationRef.current) {
            setWorkflowClusters(nextClusters);
          }
        })
        .catch((e) => {
          if (generation === loadGenerationRef.current && workflowGeneration === workflowGenerationRef.current) {
            setError(e instanceof Error ? e.message : String(e));
          }
        });

      void listKnowledgeUsageSummaryApi(config, { limit: 200, max_objects: 12 })
        .then((result) => {
          if (generation === loadGenerationRef.current && usageGeneration === usageGenerationRef.current) {
            setUsageSummary(result.objects);
          }
        })
        .catch((e) => {
          if (generation === loadGenerationRef.current && usageGeneration === usageGenerationRef.current) {
            setUsageError(e instanceof Error ? e.message : String(e));
          }
        });

      void listKnowledgeActivationUsageEventsApi(config, { limit: 12, source: "skill_activation" })
        .then((result) => {
          if (generation === loadGenerationRef.current && usageGeneration === usageGenerationRef.current) {
            setSkillActivations(result.events);
          }
        })
        .catch((e) => {
          if (generation === loadGenerationRef.current && usageGeneration === usageGenerationRef.current) {
            setUsageError(e instanceof Error ? e.message : String(e));
          }
        });
    } catch (e) {
      if (generation === loadGenerationRef.current) {
        setItems([]);
        setError(e instanceof Error ? e.message : String(e));
      }
    }
  }

  async function updateStatus(item: KnowledgeObject, status: "approved" | "rejected") {
    setBusyId(item.id);
    setError(null);
    try {
      await updateKnowledgeObjectApi(config, item.id, { status });
      await load({ refreshSnapshots: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  }

  async function publishArtifact(item: KnowledgeObject) {
    setBusyId(item.id);
    setError(null);
    try {
      await publishKnowledgeArtifactApi(config, {
        artifact_id: item.id,
        sink: "local-review",
        sink_ref: `knowledge:${item.id}`,
      });
      await load({ refreshSnapshots: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  }

  async function createSkillPromotion(item: KnowledgeObject) {
    setBusyId(item.id);
    setError(null);
    try {
      await createKnowledgeSkillPromotionApi(config, item.id);
      await load({ refreshSnapshots: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  }

  async function mergeDuplicateFacts(proposal: KnowledgeFactConsolidationProposal) {
    setBusyId(proposal.canonical_id);
    setError(null);
    try {
      await commitKnowledgeFactConsolidationApi(config, proposal);
      await load({ refreshSnapshots: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  }

  async function recordLatestUsageOutcome(row: KnowledgeUsageObjectSummary, signal: "helpful" | "irrelevant" | "harmful") {
    if (!row.last_event_id) return;
    const key = `${row.object_id}:${signal}`;
    setUsageBusyKey(key);
    setUsageError(null);
    try {
      await recordKnowledgeUsageEventOutcomeApi(config, row.last_event_id, {
        signal,
        outcome: signal,
        detail: `Marked ${signal} from Review usage summary`,
        target_object_ids: [row.object_id],
      });
      const usageGeneration = ++usageGenerationRef.current;
      const [summaryResult, skillResult] = await Promise.all([
        listKnowledgeUsageSummaryApi(config, { limit: 200, max_objects: 12 }),
        listKnowledgeActivationUsageEventsApi(config, { limit: 12, source: "skill_activation" }),
      ]);
      if (usageGeneration === usageGenerationRef.current) {
        setUsageSummary(summaryResult.objects);
        setSkillActivations(skillResult.events);
      }
    } catch (e) {
      setUsageError(e instanceof Error ? e.message : String(e));
    } finally {
      setUsageBusyKey(null);
    }
  }

  async function proposeWorkflowSkillCandidates() {
    setWorkflowBusy(true);
    setError(null);
    setWorkflowMessage(null);
    try {
      const result = await proposeKnowledgeSkillPromotionsApi(config, { limit: 1_000, min_successes: 3 });
      await load({ refreshSnapshots: true });
      setWorkflowMessage(`Created ${result.created.length} proposal${result.created.length === 1 ? "" : "s"}; skipped ${result.skipped}.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setWorkflowBusy(false);
    }
  }

  async function markWorkflowCluster(cluster: KnowledgeWorkflowCluster, status: "reviewed" | "rejected") {
    const reason = status === "rejected" ? window.prompt("Why reject this workflow cluster?", "") : null;
    if (status === "rejected" && reason === null) return;
    setWorkflowReviewBusyKey(`${cluster.id}:${status}`);
    setError(null);
    setWorkflowMessage(null);
    try {
      await reviewKnowledgeWorkflowClusterApi(config, cluster.id, { status, reason });
      await load({ refreshSnapshots: true });
      setWorkflowMessage(`Marked workflow cluster ${status}: ${cluster.title}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setWorkflowReviewBusyKey(null);
    }
  }

  async function toggleSources(item: KnowledgeObject) {
    if (sources[item.id]) {
      setSources((current) => {
        const next = { ...current };
        delete next[item.id];
        return next;
      });
      setSourceErrors((current) => {
        const next = { ...current };
        delete next[item.id];
        return next;
      });
      return;
    }
    const sourceGeneration = ++sourceGenerationRef.current;
    setSourceBusyId(item.id);
    setError(null);
    setSourceErrors((current) => {
      const next = { ...current };
      delete next[item.id];
      return next;
    });
    try {
      const result = await getKnowledgeObjectSourcesApi(config, item.id);
      if (sourceGeneration !== sourceGenerationRef.current) return;
      setSources((current) => ({ ...current, [item.id]: result }));
    } catch (e) {
      if (sourceGeneration !== sourceGenerationRef.current) return;
      setSourceErrors((current) => ({ ...current, [item.id]: e instanceof Error ? e.message : String(e) }));
    } finally {
      if (sourceGeneration === sourceGenerationRef.current) setSourceBusyId(null);
    }
  }

  useEffect(() => {
    void load();
    return () => {
      loadGenerationRef.current += 1;
      consolidationGenerationRef.current += 1;
      workflowGenerationRef.current += 1;
      usageGenerationRef.current += 1;
      sourceGenerationRef.current += 1;
    };
  }, [config]);

  const consolidationProposals = consolidation?.proposals ?? [];
  const workflowClusterItems = workflowClusters?.clusters ?? [];
  const readyWorkflowClusters = workflowClusterItems.filter((cluster) => cluster.promotion_status === "ready");
  const conflictCount = consolidation?.conflicts.length ?? 0;

  return (
    <div className="grid h-full grid-rows-[auto_minmax(0,1fr)]">
      <div className="border-b border-line-soft px-7 py-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="m-0 text-base font-semibold text-ink">Review</h3>
            <p className="m-0 mt-1 text-sm text-faint">Draft lesson candidates, actions, and artifacts that can change behavior</p>
          </div>
          <div className="flex items-center gap-2">
            {items !== null && <Pill>{items.length + consolidationProposals.length + readyWorkflowClusters.length} pending</Pill>}
            <GhostBtn onClick={() => void load({ refreshSnapshots: true })}>Refresh</GhostBtn>
          </div>
        </div>
        {error && <div className="mt-2"><ErrorPill message={error} /></div>}
      </div>

      <div className="min-h-0 overflow-y-auto scroll-thin px-7 py-5">
        <ScrollBlurTop />
        {(usageError || (usageSummary && usageSummary.length > 0) || (skillActivations && skillActivations.length > 0)) && (
          <section className="mb-5 rounded-[10px] border border-line-soft bg-bg-main/60 px-3 py-3" aria-label="Memory usage signals">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div>
                <h4 className="m-0 text-sm font-semibold text-ink-soft">Memory usage signals</h4>
                <p className="m-0 mt-1 text-xs text-faint">Recent activation usage and outcomes. Cheap summary; not full health scan.</p>
              </div>
              {usageSummary && <Pill>{usageSummary.length} memories</Pill>}
              {skillActivations && skillActivations.length > 0 && <Pill>{skillActivations.length} skill activations</Pill>}
            </div>
            {usageError ? (
              <ErrorPill message={usageError} />
            ) : (
              <>
              <ul className="m-0 grid list-none gap-2 p-0">
                {(usageSummary ?? []).map((row) => (
                  <li key={row.object_id} className="rounded-[8px] border border-line-soft bg-bg px-3 py-2 text-xs text-faint">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="min-w-0 font-medium text-ink-soft">
                        <span className="truncate">{row.object_title ?? `knowledge:${row.object_id}`}</span>
                        <span className="ml-1 text-faint">knowledge:{row.object_id}</span>
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {row.object_type && <Pill>{row.object_type}</Pill>}
                        {row.object_status && <Pill>{row.object_status}</Pill>}
                        <Pill>{row.event_count} events</Pill>
                        <Pill>{row.injected_count} injected</Pill>
                        <Pill>{row.model_visible_count} model-visible</Pill>
                        <Pill>{row.actually_used_count} observed-used</Pill>
                        {row.used_by_model_count !== row.model_visible_count && <Pill>{row.used_by_model_count} legacy-used</Pill>}
                        {row.last_seen_at && <Pill>{formatRelativePast(row.last_seen_at)}</Pill>}
                      </div>
                    </div>
                    <div className="mt-1 grid gap-1 md:grid-cols-3">
                      <div>reasons: {topCounterLabel(row.selection_reasons)}</div>
                      <div>surfaces: {topCounterLabel(row.surfaces)}</div>
                      <div>outcomes: {topCounterLabel(row.outcome_counts)}</div>
                    </div>
                    {(row.last_selection_reason || typeof row.last_activation_rank === 'number' || typeof row.last_activation_score === 'number') && (
                      <div className="mt-1 text-faint">
                        latest attribution: {row.last_selection_reason ?? 'unknown'}
                        {row.last_activation_state && ` · state ${row.last_activation_state}`}
                        {typeof row.last_model_visible === 'boolean' && ` · visible ${row.last_model_visible ? 'yes' : 'no'}`}
                        {typeof row.last_actual_use_observed === 'boolean' && ` · observed-use ${row.last_actual_use_observed ? 'yes' : 'no'}`}
                        {typeof row.last_activation_rank === 'number' && ` · rank ${row.last_activation_rank}`}
                        {typeof row.last_activation_score === 'number' && ` · score ${row.last_activation_score.toFixed(2)}`}
                        {row.last_activation_surface && ` · ${row.last_activation_surface}`}
                        {row.last_activation_task_id && ` · task ${row.last_activation_task_id}`}
                        {row.last_activation_run_id && ` · run ${row.last_activation_run_id}`}
                      </div>
                    )}
                    {row.last_event_id && (
                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        <span className="text-faint">Mark latest event:</span>
                        <GhostBtn disabled={usageBusyKey !== null} onClick={() => void recordLatestUsageOutcome(row, "helpful")}>
                          {usageBusyKey === `${row.object_id}:helpful` ? "Saving..." : "Helpful"}
                        </GhostBtn>
                        <GhostBtn disabled={usageBusyKey !== null} onClick={() => void recordLatestUsageOutcome(row, "irrelevant")}>
                          {usageBusyKey === `${row.object_id}:irrelevant` ? "Saving..." : "Irrelevant"}
                        </GhostBtn>
                        <GhostBtn disabled={usageBusyKey !== null} onClick={() => void recordLatestUsageOutcome(row, "harmful")}>
                          {usageBusyKey === `${row.object_id}:harmful` ? "Saving..." : "Harmful"}
                        </GhostBtn>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
              <SkillActivationList events={skillActivations} />
              </>
            )}
          </section>
        )}
        {workflowClusterItems.length > 0 && (
          <section className="mb-5 rounded-[10px] border border-line-soft bg-bg-main/60 px-3 py-3" aria-label="Workflow skill clusters">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div>
                <h4 className="m-0 text-sm font-semibold text-ink-soft">Workflow skill clusters</h4>
                <p className="m-0 mt-1 text-xs text-faint">Repeated workflows mined from lessons before they become approved skills.</p>
              </div>
              <div className="flex flex-wrap gap-1.5">
                <Pill>{workflowClusterItems.length} clusters</Pill>
                {readyWorkflowClusters.length > 0 && <Pill>{readyWorkflowClusters.length} ready</Pill>}
                {readyWorkflowClusters.length > 0 && (
                  <GhostBtn onClick={() => void proposeWorkflowSkillCandidates()} disabled={workflowBusy}>
                    {workflowBusy ? "Creating…" : "Create proposals"}
                  </GhostBtn>
                )}
                {workflowClusters?.cache && (
                  <Pill>{workflowClusters.cache.hit ? "cached snapshot" : "fresh snapshot"}</Pill>
                )}
              </div>
            </div>
            {workflowMessage && <p className="m-0 mb-3 text-xs text-muted">{workflowMessage}</p>}
            <div className="grid gap-2">
              {workflowClusterItems.slice(0, 8).map((cluster) => (
                <div key={cluster.id} className="rounded-[8px] border border-line-soft bg-bg-main/70 p-3">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <div className="text-sm font-medium text-ink">{cluster.title}</div>
                      <div className="mt-1 text-xs text-faint">{cluster.id}</div>
                      {cluster.summary && <p className="m-0 mt-2 text-xs text-muted">{cluster.summary}</p>}
                      {cluster.trigger_description && (
                        <div className="mt-1 text-[11px] text-faint">Trigger: {cluster.trigger_description}</div>
                      )}
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      <Pill>{cluster.status}</Pill>
                      <Pill>{cluster.promotion_status}</Pill>
                      <Pill>{cluster.lesson_count} lessons</Pill>
                      {cluster.usage_event_count > 0 && <Pill>{cluster.usage_event_count} usage events</Pill>}
                      {cluster.last_seen_at && <Pill>last seen {new Date(cluster.last_seen_at).toLocaleDateString()}</Pill>}
                      <Pill>{cluster.success_count} successes</Pill>
                      <Pill>{cluster.helpful_count} helpful</Pill>
                      <Pill>{cluster.failure_count} failures</Pill>
                      <Pill>{cluster.correction_count} corrections</Pill>
                    </div>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <GhostBtn
                      onClick={() => void markWorkflowCluster(cluster, "reviewed")}
                      disabled={workflowReviewBusyKey !== null || cluster.status === "reviewed" || cluster.status === "promoted"}
                    >
                      {workflowReviewBusyKey === `${cluster.id}:reviewed` ? "Marking…" : "Mark reviewed"}
                    </GhostBtn>
                    <GhostBtn
                      onClick={() => void markWorkflowCluster(cluster, "rejected")}
                      disabled={workflowReviewBusyKey !== null || cluster.status === "rejected" || cluster.status === "promoted"}
                    >
                      {workflowReviewBusyKey === `${cluster.id}:rejected` ? "Rejecting…" : "Reject"}
                    </GhostBtn>
                  </div>
                  <p className="m-0 mt-2 text-xs text-faint">{cluster.why_should_exist}</p>
                  <WorkflowReviewMarkerDetails cluster={cluster} />
                  <div className="mt-2 flex flex-wrap gap-1.5 text-[11px] text-faint">
                    {cluster.source_lesson_ids.slice(0, 8).map((id) => (
                      <span key={id} className="rounded-full border border-line-soft px-2 py-0.5">knowledge:{id}</span>
                    ))}
                    {cluster.source_lesson_ids.length > 8 && <span>+{cluster.source_lesson_ids.length - 8} more lessons</span>}
                    {cluster.source_episode_ids.slice(0, 4).map((id) => (
                      <span key={`episode-${id}`} className="rounded-full border border-line-soft px-2 py-0.5">{id}</span>
                    ))}
                    {cluster.source_artifact_ids.slice(0, 4).map((id) => (
                      <span key={`artifact-${id}`} className="rounded-full border border-line-soft px-2 py-0.5">{id}</span>
                    ))}
                    {cluster.skill_candidate_ids.map((id) => (
                      <span key={`candidate-${id}`} className="rounded-full border border-line-soft px-2 py-0.5">candidate:{id}</span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}
        {consolidationProposals.length > 0 && (
          <section className="mb-5 rounded-[10px] border border-line-soft bg-bg-main/60 px-3 py-3" aria-label="Fact consolidation proposals">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div>
                <h4 className="m-0 text-sm font-semibold text-ink-soft">Duplicate facts</h4>
                <p className="m-0 mt-1 text-xs text-faint">Manual merge proposals. The canonical fact keeps rolled-up sources; duplicates become superseded.</p>
              </div>
              <div className="flex flex-wrap gap-1.5">
                <Pill>{consolidationProposals.length} merge proposals</Pill>
                {consolidation?.cache && (
                  <Pill>{consolidation.cache.hit ? "cached snapshot" : "fresh snapshot"}</Pill>
                )}
                {conflictCount > 0 && <Pill>{conflictCount} conflicts held</Pill>}
              </div>
            </div>
            <ul className="m-0 grid list-none gap-3 p-0">
              {consolidationProposals.map((proposal) => (
                <li key={`${proposal.canonical_id}-${proposal.duplicate_ids.join("-")}`} className="rounded-[8px] border border-line-soft bg-bg-main px-2 py-2">
                  <div className="mb-1 flex flex-wrap items-center gap-1.5">
                    <Pill>{Math.round(proposal.confidence * 100)}% confidence</Pill>
                    <Pill>{proposal.duplicate_ids.length} duplicates</Pill>
                    {proposal.source_ids.length > 0 && <Pill>{proposal.source_ids.length} sources</Pill>}
                  </div>
                  <p className="m-0 text-sm font-semibold text-ink-soft">Keep: {proposal.canonical_title}</p>
                  <p className="m-0 mt-1 whitespace-pre-wrap text-xs leading-snug text-faint">{proposal.canonical_text}</p>
                  <div className="mt-2 rounded-md border border-line-soft bg-bg-main/50 px-2 py-2">
                    <p className="m-0 mb-1 text-xs font-semibold uppercase tracking-[0.08em] text-faint">Supersede</p>
                    <ul className="m-0 grid list-none gap-1 p-0">
                      {proposal.duplicate_titles.map((title, index) => (
                        <li key={`${proposal.duplicate_ids[index]}-${title}`} className="text-xs leading-snug text-ink-soft">
                          <span className="font-mono text-faint">#{proposal.duplicate_ids[index]}</span> · {title}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <p className="m-0 mt-2 text-xs text-faint">{proposal.reason}</p>
                  {proposal.evidence_terms.length > 0 && <p className="m-0 mt-1 text-xs text-faint">Evidence: {proposal.evidence_terms.slice(0, 8).join(", ")}</p>}
                  <div className="mt-3 flex flex-wrap gap-2">
                    <GhostBtn disabled={busyId === proposal.canonical_id} onClick={() => void mergeDuplicateFacts(proposal)}>
                      {busyId === proposal.canonical_id ? "Merging..." : "Merge duplicates"}
                    </GhostBtn>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        )}
        {items === null ? (
          <div className="grid h-full place-items-center text-base italic text-faint">Loading</div>
        ) : items.length === 0 && consolidationProposals.length === 0 ? (
          <div className="grid h-full place-items-center text-base italic text-faint">Nothing needs review</div>
        ) : items.length === 0 ? null : (
          <ul className="m-0 grid list-none gap-3 p-0">
            {items.map((item) => (
              <li key={item.id} className="rounded-[8px] border border-line-soft bg-bg-main/50 px-3 py-3">
                <div className="mb-1 flex flex-wrap items-center gap-1.5">
                  <Pill>{reviewKind(item)}</Pill>
                  <Pill>{item.proactiveness_level}</Pill>
                  {item.scope && <Pill>{item.scope}</Pill>}
                  <span className="text-xs text-faint">updated {formatRelativePast(item.updated_at)}</span>
                </div>
                <h4 className="m-0 text-sm font-semibold text-ink-soft">{item.title}</h4>
                <p className="m-0 mt-1 whitespace-pre-wrap text-sm leading-snug text-ink-soft">{item.text}</p>
                <p className="m-0 mt-2 text-xs text-faint">{reviewOutcomeHint(item)}</p>
                <ReviewEvidence item={item} />
                {(sources[item.id] || sourceErrors[item.id]) && (
                  <div id={`review-sources-${item.id}`} className="mt-3 rounded-md border border-line-soft bg-bg-main px-2 py-2">
                    <p className="m-0 mb-2 text-xs font-semibold uppercase tracking-[0.08em] text-faint">Sources</p>
                    {sourceErrors[item.id] ? (
                      <ErrorPill message={sourceErrors[item.id]} />
                    ) : sources[item.id].sources.length === 0 ? (
                      <p className="m-0 text-xs italic text-faint">No source trace</p>
                    ) : (
                      <ul className="m-0 grid list-none gap-2 p-0">
                        {sources[item.id].sources.map((source) => (
                          <li key={source.source_id} className="text-xs leading-snug text-ink-soft">
                            <span className="font-mono text-faint">{source.source_id}</span>
                            {source.object && <span> · {source.object.object_type}: {source.object.title}</span>}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
                <div className="mt-3 flex flex-wrap gap-2">
                  {item.object_type === "artifact" ? (
                    <GhostBtn disabled={busyId === item.id || sourceBusyId === item.id} onClick={() => void publishArtifact(item)}>Publish</GhostBtn>
                  ) : isSkillPromotionCandidate(item) ? (
                    <GhostBtn disabled={busyId === item.id || sourceBusyId === item.id} onClick={() => void createSkillPromotion(item)}>
                      {reviewActionLabel(item)}
                    </GhostBtn>
                  ) : (
                    <GhostBtn disabled={busyId === item.id || sourceBusyId === item.id} onClick={() => void updateStatus(item, "approved")}>
                      {reviewActionLabel(item)}
                    </GhostBtn>
                  )}
                  <GhostBtn disabled={busyId === item.id || sourceBusyId === item.id} onClick={() => void updateStatus(item, "rejected")}>Dismiss</GhostBtn>
                  <GhostBtn
                    disabled={busyId === item.id || sourceBusyId === item.id}
                    onClick={() => void toggleSources(item)}
                    aria-expanded={Boolean(sources[item.id])}
                    aria-controls={`review-sources-${item.id}`}
                  >
                    {sourceBusyId === item.id ? "Loading sources..." : sources[item.id] ? "Hide sources" : "Sources"}
                  </GhostBtn>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
