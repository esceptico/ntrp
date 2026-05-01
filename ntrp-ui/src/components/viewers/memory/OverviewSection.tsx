import type {
  Fact,
  MemoryAccessEvent,
  MemoryAudit,
  MemoryEvent,
  MemoryInjectionPolicyPreview,
  MemoryProfilePolicyPreview,
  MemoryPruneDryRun,
  MemoryStorageHealth,
} from "../../../api/client.js";
import { colors, truncateText } from "../../ui/index.js";
import { useAccentColor } from "../../../hooks/index.js";
import { formatTimeAgo } from "../../../lib/format.js";
import { memoryAccessSourceLabel } from "../../../lib/memoryAccess.js";

interface OverviewSectionProps {
  profileFacts: Fact[];
  memoryProfilePolicy: MemoryProfilePolicyPreview | null;
  factTotal: number;
  observationTotal: number;
  pruneDryRun: MemoryPruneDryRun | null;
  memoryEvents: MemoryEvent[];
  memoryAccessEvents: MemoryAccessEvent[];
  memoryInjectionPolicy: MemoryInjectionPolicyPreview | null;
  memoryAudit: MemoryAudit | null;
  height: number;
  width: number;
}

const PROFILE_REASON_LABELS: Record<string, string> = {
  pinned_non_profile: "pinned non-profile",
  important_non_profile: "important non-profile",
  reused_non_profile: "reused non-profile",
  profile_overlong: "overlong",
  profile_low_confidence: "low confidence",
};

function MetricRow({ label, value, note }: { label: string; value: string | number; note: string }) {
  return (
    <text>
      <span fg={colors.text.secondary}>{label}</span>
      <span fg={colors.text.disabled}> {"\u2502"} </span>
      <span fg={colors.text.primary}>{value}</span>
      <span fg={colors.text.disabled}> {"\u2502"} {note}</span>
    </text>
  );
}

function storageIssueCount(storage: MemoryStorageHealth | undefined): number {
  if (!storage) return 0;
  return storage.missing_vec_rows + storage.stale_vec_rows + storage.missing_fts_rows + storage.stale_fts_rows;
}

function relationIssueCount(relations: Record<string, number> | undefined): number {
  if (!relations) return 0;
  return Object.values(relations).reduce((sum, value) => sum + value, 0);
}

export function OverviewSection({
  profileFacts,
  memoryProfilePolicy,
  factTotal,
  observationTotal,
  pruneDryRun,
  memoryEvents,
  memoryAccessEvents,
  memoryInjectionPolicy,
  memoryAudit,
  height,
  width,
}: OverviewSectionProps) {
  const { accentValue } = useAccentColor();
  const latestEvent = memoryEvents[0];
  const latestAccess = memoryAccessEvents[0];
  const storageIssues =
    storageIssueCount(memoryAudit?.storage.facts) + storageIssueCount(memoryAudit?.storage.observations);
  const relationIssues = relationIssueCount(memoryAudit?.relations);
  const missingEmbeddings = (memoryAudit?.facts.no_embedding ?? 0) + (memoryAudit?.observations.no_embedding ?? 0);
  const profileReviewCount =
    (memoryProfilePolicy?.summary.candidates ?? 0) + (memoryProfilePolicy?.summary.issues ?? 0);
  const topProfileReview = memoryProfilePolicy?.candidates[0] ?? memoryProfilePolicy?.issues[0] ?? null;
  const profileReviewLabel = topProfileReview
    ? topProfileReview.reasons.map((reason) => PROFILE_REASON_LABELS[reason] ?? reason).join(", ")
    : "";

  return (
    <box flexDirection="column" width={width} height={height} paddingLeft={1} overflow="hidden">
      <text>
        <span fg={accentValue}>memory overview</span>
        <span fg={colors.text.disabled}> {"\u2502"} current health and control surface</span>
      </text>

      <box flexDirection="column" marginTop={2}>
        <MetricRow label="Profile" value={profileFacts.length} note="always-on facts shown to the agent first" />
        <MetricRow label="Profile review" value={profileReviewCount} note="profile candidates and quality flags" />
        <MetricRow label="Recall" value="query" note="inspect retrieved context before it reaches the agent" />
        <MetricRow label="Used" value={memoryAccessEvents.length} note="recent memory bundles injected into prompts/tools" />
        <MetricRow
          label="Policy"
          value={memoryInjectionPolicy?.summary.candidates ?? 0}
          note="recent injected-memory bundles worth reviewing"
        />
        <MetricRow label="Facts" value={factTotal} note="source-of-truth memory records" />
        <MetricRow label="Patterns" value={observationTotal} note="derived summaries with supporting facts" />
        <MetricRow label="Embeddings" value={missingEmbeddings} note="active rows missing vectors" />
        <MetricRow label="Storage" value={storageIssues} note="vec/FTS index rows needing repair" />
        <MetricRow label="Relations" value={relationIssues} note="orphaned provenance/entity links" />
        <MetricRow
          label="Cleanup"
          value={pruneDryRun?.summary.total ?? 0}
          note="archive candidates matching the current cleanup rule"
        />
        <MetricRow label="Log" value={memoryEvents.length} note="recent memory writes and automation outcomes loaded" />
      </box>

      <box flexDirection="column" marginTop={2}>
        <text><span fg={colors.text.muted}>OPEN NEXT</span></text>
        <text><span fg={colors.text.secondary}>Recall</span><span fg={colors.text.disabled}> to debug query-time memory retrieval</span></text>
        <text><span fg={colors.text.secondary}>Used</span><span fg={colors.text.disabled}> to inspect what memory reached the model</span></text>
        <text><span fg={colors.text.secondary}>Policy</span><span fg={colors.text.disabled}> flags appear inside Used when context looks noisy</span></text>
        <text><span fg={colors.text.secondary}>Profile</span><span fg={colors.text.disabled}> for what the agent should always know</span></text>
        <text><span fg={colors.text.secondary}>Facts</span><span fg={colors.text.disabled}> to edit durable truth</span></text>
        <text><span fg={colors.text.secondary}>Patterns</span><span fg={colors.text.disabled}> to inspect derived memory and provenance</span></text>
        <text><span fg={colors.text.secondary}>Cleanup</span><span fg={colors.text.disabled}> to archive low-value patterns in bulk</span></text>
        <text><span fg={colors.text.secondary}>Log</span><span fg={colors.text.disabled}> to answer why memory changed</span></text>
      </box>

      <box flexDirection="column" marginTop={2}>
        <text><span fg={colors.text.muted}>PROFILE REVIEW</span></text>
        {topProfileReview ? (
          <text>
            <span fg={colors.text.secondary}>#{topProfileReview.fact.id}</span>
            <span fg={colors.text.disabled}> {"\u2502"} {profileReviewLabel}</span>
            <span fg={colors.text.disabled}> {"\u2502"} {truncateText(topProfileReview.recommendation, width - 28)}</span>
          </text>
        ) : (
          <text><span fg={colors.text.disabled}>No profile policy flags loaded</span></text>
        )}
      </box>

      <box flexDirection="column" marginTop={1}>
        <text><span fg={colors.text.muted}>LATEST USED MEMORY</span></text>
        {latestAccess ? (
          <text>
            <span fg={colors.text.secondary}>{memoryAccessSourceLabel(latestAccess.source)}</span>
            <span fg={colors.text.disabled}> {"\u2502"} {latestAccess.injected_fact_ids.length} facts</span>
            <span fg={colors.text.disabled}> / {latestAccess.injected_observation_ids.length} patterns</span>
            <span fg={colors.text.disabled}> {"\u2502"} {formatTimeAgo(latestAccess.created_at)}</span>
          </text>
        ) : (
          <text><span fg={colors.text.disabled}>No context injections loaded</span></text>
        )}
      </box>

      <box flexDirection="column" marginTop={1}>
        <text><span fg={colors.text.muted}>LATEST LOG</span></text>
        {latestEvent ? (
          <text>
            <span fg={colors.text.secondary}>{latestEvent.action}</span>
            <span fg={colors.text.disabled}> {"\u2502"} {latestEvent.actor}</span>
            <span fg={colors.text.disabled}> {"\u2502"} {formatTimeAgo(latestEvent.created_at)}</span>
          </text>
        ) : (
          <text><span fg={colors.text.disabled}>No memory log entries loaded</span></text>
        )}
      </box>
    </box>
  );
}
