import type {
  Fact,
  LearningCandidate,
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
import { learningChangeLabel } from "../../../lib/memoryLearning.js";

interface OverviewSectionProps {
  profileFacts: Fact[];
  memoryProfilePolicy: MemoryProfilePolicyPreview | null;
  factTotal: number;
  observationTotal: number;
  pruneDryRun: MemoryPruneDryRun | null;
  memoryEvents: MemoryEvent[];
  learningCandidates: LearningCandidate[];
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

function filledText(text: string, width: number): string {
  if (width <= 0) return "";
  return truncateText(text, width).padEnd(width);
}

interface LineSegment {
  text: string;
  fg: string;
  width?: number;
}

function OverviewLine({ segments, width }: { segments: LineSegment[]; width: number }) {
  const bg = colors.background.element ?? colors.background.menu;
  let used = 0;
  const rendered = segments.map((segment, index) => {
    const remaining = Math.max(0, width - used);
    const segmentWidth = Math.min(segment.width ?? remaining, remaining);
    if (segmentWidth <= 0) return null;
    used += segmentWidth;
    return (
      <span key={index} fg={segment.fg} bg={bg}>
        {filledText(segment.text, segmentWidth)}
      </span>
    );
  });
  const rest = Math.max(0, width - used);

  return (
    <text>
      {rendered}
      {rest > 0 && <span bg={bg}>{filledText("", rest)}</span>}
    </text>
  );
}

function MetricRow({ label, value, note, width }: { label: string; value: string | number; note: string; width: number }) {
  return (
    <OverviewLine
      width={width}
      segments={[
        { text: label, fg: colors.text.secondary, width: 16 },
        { text: " | ", fg: colors.text.disabled, width: 3 },
        { text: String(value), fg: colors.text.primary, width: 8 },
        { text: " | ", fg: colors.text.disabled, width: 3 },
        { text: note, fg: colors.text.secondary },
      ]}
    />
  );
}

function ActionRow({ keyName, label, note, width }: { keyName: string; label: string; note: string; width: number }) {
  return (
    <OverviewLine
      width={width}
      segments={[
        { text: keyName, fg: colors.text.primary, width: 3 },
        { text: label, fg: colors.text.secondary, width: 10 },
        { text: note, fg: colors.text.secondary },
      ]}
    />
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
  learningCandidates,
  memoryAccessEvents,
  memoryInjectionPolicy,
  memoryAudit,
  height,
  width,
}: OverviewSectionProps) {
  const { accentValue } = useAccentColor();
  const latestEvent = memoryEvents[0];
  const latestLearningCandidate = learningCandidates[0];
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
  const textWidth = Math.max(1, width - 1);

  return (
    <box flexDirection="column" width={width} height={height} paddingLeft={1} overflow="hidden">
      <OverviewLine
        width={textWidth}
        segments={[
          { text: "memory overview", fg: accentValue, width: 16 },
          { text: " | ", fg: colors.text.disabled, width: 3 },
          { text: "facts are truth, patterns are derived, sent memory is runtime evidence", fg: colors.text.secondary },
        ]}
      />

      <box flexDirection="column" marginTop={2}>
        <MetricRow label="Profile" value={profileFacts.length} note="always-on facts shown to the agent first" width={textWidth} />
        <MetricRow label="Profile review" value={profileReviewCount} note="profile candidates and quality flags" width={textWidth} />
        <MetricRow label="Search" value="query" note="test retrieval before it reaches the agent" width={textWidth} />
        <MetricRow label="Sent" value={memoryAccessEvents.length} note="recent memory bundles injected into prompts/tools" width={textWidth} />
        <MetricRow
          label="Policy"
          value={memoryInjectionPolicy?.summary.candidates ?? 0}
          note="recent injected-memory bundles worth reviewing"
          width={textWidth}
        />
        <MetricRow label="Facts" value={factTotal} note="source-of-truth memory records" width={textWidth} />
        <MetricRow label="Patterns" value={observationTotal} note="derived summaries with supporting facts" width={textWidth} />
        <MetricRow label="Embeddings" value={missingEmbeddings} note="active rows missing vectors" width={textWidth} />
        <MetricRow label="Storage" value={storageIssues} note="vec/FTS index rows needing repair" width={textWidth} />
        <MetricRow label="Relations" value={relationIssues} note="orphaned provenance/entity links" width={textWidth} />
        <MetricRow
          label="Cleanup"
          value={pruneDryRun?.summary.total ?? 0}
          note="archive candidates matching the current cleanup rule"
          width={textWidth}
        />
        <MetricRow label="Improve" value={learningCandidates.length} note="reviewable policy, skill, and prompt candidates" width={textWidth} />
        <MetricRow label="Audit" value={memoryEvents.length} note="recent memory writes and automation outcomes loaded" width={textWidth} />
      </box>

      <box flexDirection="column" marginTop={2}>
        <OverviewLine width={textWidth} segments={[{ text: "TAB MAP", fg: accentValue }]} />
        <ActionRow keyName="1" label="Home" note="memory health and navigation map" width={textWidth} />
        <ActionRow keyName="2" label="Search" note="debug query-time memory retrieval" width={textWidth} />
        <ActionRow keyName="3" label="Sent" note="inspect what memory reached the model" width={textWidth} />
        <ActionRow keyName="4" label="Profile" note="edit always-visible facts" width={textWidth} />
        <ActionRow keyName="5" label="Facts" note="edit durable truth" width={textWidth} />
        <ActionRow keyName="6" label="Patterns" note="inspect derived memory and provenance" width={textWidth} />
        <ActionRow keyName="7" label="Cleanup" note="archive low-value patterns in bulk" width={textWidth} />
        <ActionRow keyName="8" label="Improve" note="review proposed durable improvements" width={textWidth} />
        <ActionRow keyName="9" label="Audit" note="answer why memory changed" width={textWidth} />
      </box>

      <box flexDirection="column" marginTop={2}>
        <OverviewLine width={textWidth} segments={[{ text: "PROFILE REVIEW", fg: accentValue }]} />
        {topProfileReview ? (
          <OverviewLine
            width={textWidth}
            segments={[
              { text: topProfileReview.fact.text, fg: colors.text.secondary, width: Math.max(12, Math.floor(textWidth * 0.45)) },
              { text: " | ", fg: colors.text.disabled, width: 3 },
              { text: profileReviewLabel, fg: colors.text.secondary, width: 24 },
              { text: " | ", fg: colors.text.disabled, width: 3 },
              { text: topProfileReview.recommendation, fg: colors.text.secondary },
            ]}
          />
        ) : (
          <OverviewLine width={textWidth} segments={[{ text: "No profile policy flags loaded", fg: colors.text.disabled }]} />
        )}
      </box>

      <box flexDirection="column" marginTop={1}>
        <OverviewLine width={textWidth} segments={[{ text: "LATEST SENT MEMORY", fg: accentValue }]} />
        {latestAccess ? (
          <OverviewLine
            width={textWidth}
            segments={[
              { text: memoryAccessSourceLabel(latestAccess.source), fg: colors.text.secondary, width: 18 },
              { text: " | ", fg: colors.text.disabled, width: 3 },
              { text: `${latestAccess.injected_fact_ids.length} facts / ${latestAccess.injected_observation_ids.length} patterns`, fg: colors.text.secondary, width: 22 },
              { text: " | ", fg: colors.text.disabled, width: 3 },
              { text: formatTimeAgo(latestAccess.created_at), fg: colors.text.secondary },
            ]}
          />
        ) : (
          <OverviewLine width={textWidth} segments={[{ text: "No context injections loaded", fg: colors.text.disabled }]} />
        )}
      </box>

      <box flexDirection="column" marginTop={1}>
        <OverviewLine width={textWidth} segments={[{ text: "LATEST LEARNING", fg: accentValue }]} />
        {latestLearningCandidate ? (
          <OverviewLine
            width={textWidth}
            segments={[
              { text: latestLearningCandidate.status, fg: colors.text.secondary, width: 12 },
              { text: " | ", fg: colors.text.disabled, width: 3 },
              { text: learningChangeLabel(latestLearningCandidate.change_type), fg: colors.text.secondary, width: 20 },
              { text: " | ", fg: colors.text.disabled, width: 3 },
              { text: latestLearningCandidate.proposal, fg: colors.text.secondary },
            ]}
          />
        ) : (
          <OverviewLine width={textWidth} segments={[{ text: "No learning candidates loaded", fg: colors.text.disabled }]} />
        )}
      </box>

      <box flexDirection="column" marginTop={1}>
        <OverviewLine width={textWidth} segments={[{ text: "LATEST LOG", fg: accentValue }]} />
        {latestEvent ? (
          <OverviewLine
            width={textWidth}
            segments={[
              { text: latestEvent.action, fg: colors.text.secondary, width: 22 },
              { text: " | ", fg: colors.text.disabled, width: 3 },
              { text: latestEvent.actor, fg: colors.text.secondary, width: 16 },
              { text: " | ", fg: colors.text.disabled, width: 3 },
              { text: formatTimeAgo(latestEvent.created_at), fg: colors.text.secondary },
            ]}
          />
        ) : (
          <OverviewLine width={textWidth} segments={[{ text: "No memory log entries loaded", fg: colors.text.disabled }]} />
        )}
      </box>
    </box>
  );
}
