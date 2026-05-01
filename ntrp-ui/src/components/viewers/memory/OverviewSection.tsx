import type {
  LearningCandidate,
  MemoryAccessEvent,
  MemoryAudit,
  MemoryEvent,
  MemoryInjectionPolicyPreview,
  MemoryPruneDryRun,
  MemoryStorageHealth,
} from "../../../api/client.js";
import { useAccentColor } from "../../../hooks/index.js";
import { summarizeLearningCandidates } from "../../../lib/memoryLearning.js";
import { truncateText } from "../../../lib/utils.js";
import { colors } from "../../ui/index.js";

interface OverviewSectionProps {
  factTotal: number;
  observationTotal: number;
  pruneDryRun: MemoryPruneDryRun | null;
  memoryEvents: MemoryEvent[];
  learningCandidates: LearningCandidate[];
  memoryAccessEvents: MemoryAccessEvent[];
  profileCount: number;
  memoryInjectionPolicy: MemoryInjectionPolicyPreview | null;
  memoryAudit: MemoryAudit | null;
  height: number;
  width: number;
}

interface LineSegment {
  text: string;
  fg: string;
  width?: number;
}

function cell(text: string, width: number): string {
  if (width <= 0) return "";
  return truncateText(text, width).padEnd(width);
}

function OverviewLine({ segments, width }: { segments: LineSegment[]; width: number }) {
  let used = 0;
  return (
    <text>
      {segments.map((segment, index) => {
        const remaining = Math.max(0, width - used);
        const segmentWidth = Math.min(segment.width ?? remaining, remaining);
        if (segmentWidth <= 0) return null;
        used += segmentWidth;
        return (
          <span key={index} fg={segment.fg}>
            {cell(segment.text, segmentWidth)}
          </span>
        );
      })}
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
        { text: keyName, fg: colors.text.primary, width: 2 },
        { text: label, fg: colors.text.secondary, width: 9 },
        { text: note, fg: colors.text.secondary },
      ]}
    />
  );
}

function CompactActionRow({ actions, width }: { actions: [string, string, string][]; width: number }) {
  const noteWidth = Math.max(8, Math.floor((width - 39) / 3));
  return (
    <OverviewLine
      width={width}
      segments={actions.flatMap(([keyName, label, note], index) => [
        ...(index > 0 ? [{ text: "  ", fg: colors.text.disabled, width: 2 }] : []),
        { text: keyName, fg: colors.text.primary, width: 2 },
        { text: label, fg: colors.text.secondary, width: 9 },
        { text: note, fg: colors.text.disabled, width: noteWidth },
      ])}
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
  factTotal,
  observationTotal,
  pruneDryRun,
  memoryEvents,
  learningCandidates,
  memoryAccessEvents,
  profileCount,
  memoryInjectionPolicy,
  memoryAudit,
  height,
  width,
}: OverviewSectionProps) {
  const { accentValue } = useAccentColor();
  const textWidth = Math.max(1, width - 1);
  const compact = height < 24;
  const storageIssues =
    storageIssueCount(memoryAudit?.storage.facts) + storageIssueCount(memoryAudit?.storage.observations);
  const relationIssues = relationIssueCount(memoryAudit?.relations);
  const missingEmbeddings = (memoryAudit?.facts.no_embedding ?? 0) + (memoryAudit?.observations.no_embedding ?? 0);
  const policyReviewCount = memoryInjectionPolicy?.summary.candidates ?? 0;
  const cleanupCount = pruneDryRun?.summary.total ?? 0;
  const learningSummary = summarizeLearningCandidates(learningCandidates);

  return (
    <box flexDirection="column" width={width} height={height} paddingLeft={1} overflow="hidden">
      <OverviewLine
        width={textWidth}
        segments={[
          { text: "memory overview", fg: accentValue, width: 16 },
          { text: " | ", fg: colors.text.disabled, width: 3 },
          { text: "patterns are contextual memory; profile is explicit; facts are evidence", fg: colors.text.secondary },
        ]}
      />

      <box flexDirection="column" marginTop={2}>
        <OverviewLine width={textWidth} segments={[{ text: "ATTENTION", fg: accentValue }]} />
        <MetricRow
          label="Sent policy"
          value={policyReviewCount}
          note={policyReviewCount > 0 ? "review injected-memory bundles" : "clean"}
          width={textWidth}
        />
        <MetricRow
          label="Cleanup"
          value={cleanupCount}
          note={cleanupCount > 0 ? "bulk archive candidates ready" : "clean"}
          width={textWidth}
        />
        <MetricRow
          label="Improve"
          value={learningSummary.needsAction}
          note={
            learningSummary.needsAction > 0
              ? `${learningSummary.proposed} review, ${learningSummary.readyToApply} apply, ${learningSummary.active} active`
              : learningSummary.active > 0
                ? `${learningSummary.active} active, no pending review`
              : "no proposals"
          }
          width={textWidth}
        />
      </box>

      <box flexDirection="column" marginTop={2}>
        <OverviewLine width={textWidth} segments={[{ text: "INVENTORY", fg: accentValue }]} />
        <MetricRow label="Profile" value={profileCount} note="explicit always-profile facts" width={textWidth} />
        <MetricRow label="Facts" value={factTotal} note="source-of-truth memory records" width={textWidth} />
        <MetricRow label="Patterns" value={observationTotal} note="contextual summaries with supporting facts" width={textWidth} />
        <MetricRow label="Sent" value={memoryAccessEvents.length} note="recent memory bundles injected into prompts/tools" width={textWidth} />
        <MetricRow label="Audit" value={memoryEvents.length} note="recent memory writes and automation outcomes loaded" width={textWidth} />
        {!compact && (
          <>
            <MetricRow label="Embeddings" value={missingEmbeddings} note="active rows missing vectors" width={textWidth} />
            <MetricRow label="Storage" value={storageIssues} note="vec/FTS index rows needing repair" width={textWidth} />
            <MetricRow label="Relations" value={relationIssues} note="orphaned provenance/entity links" width={textWidth} />
          </>
        )}
      </box>

      <box flexDirection="column" marginTop={2}>
        <OverviewLine width={textWidth} segments={[{ text: "NAVIGATION", fg: accentValue }]} />
        {width >= 96 ? (
          <>
            <CompactActionRow
              width={textWidth}
              actions={[
                ["2", "Search", "test recall"],
                ["3", "Sent", "model memory"],
                ["4", "Profile", "explicit"],
              ]}
            />
            <CompactActionRow
              width={textWidth}
              actions={[
                ["5", "Facts", "evidence"],
                ["6", "Patterns", "context"],
                ["7", "Cleanup", "archive"],
              ]}
            />
            <CompactActionRow
              width={textWidth}
              actions={[
                ["8", "Improve", "proposals"],
                ["9", "Audit", "history"],
              ]}
            />
          </>
        ) : (
          <>
            <ActionRow keyName="1" label="Home" note="memory health and navigation map" width={textWidth} />
            <ActionRow keyName="2" label="Search" note="debug query-time memory retrieval" width={textWidth} />
            <ActionRow keyName="3" label="Sent" note="inspect what memory reached the model" width={textWidth} />
            <ActionRow keyName="4" label="Profile" note="inspect or edit explicit always-profile facts" width={textWidth} />
            <ActionRow keyName="5" label="Facts" note="inspect or edit source evidence" width={textWidth} />
            <ActionRow keyName="6" label="Patterns" note="inspect contextual summaries and provenance" width={textWidth} />
            <ActionRow keyName="7" label="Cleanup" note="archive low-value patterns in bulk" width={textWidth} />
            <ActionRow keyName="8" label="Improve" note="review proposed durable improvements" width={textWidth} />
            <ActionRow keyName="9" label="Audit" note="answer why memory changed" width={textWidth} />
          </>
        )}
      </box>
    </box>
  );
}
