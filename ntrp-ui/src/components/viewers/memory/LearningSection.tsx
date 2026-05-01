import type { LearningCandidate, LearningEvent } from "../../../api/client.js";
import { useAccentColor } from "../../../hooks/index.js";
import type { LearningTabState } from "../../../hooks/useLearningTab.js";
import { formatTimeAgo, shortTime } from "../../../lib/format.js";
import { cleanLearningText, learningDetailRows, summarizeLearningEvidence } from "../../../lib/memoryLearningDetails.js";
import { learningCandidateEffect, learningChangeLabel } from "../../../lib/memoryLearning.js";
import { colors, truncateText, type RenderItemContext } from "../../ui/index.js";
import { ListDetailSection } from "./ListDetailSection.js";

interface LearningSectionProps {
  tab: LearningTabState;
  totalCount: number;
  height: number;
  width: number;
}

function statusColor(status: string, accent: string): string {
  switch (status) {
    case "approved":
      return accent;
    case "applied":
      return colors.status.success;
    case "rejected":
    case "reverted":
      return colors.text.disabled;
    default:
      return colors.status.warning;
  }
}

function DetailsSummary({ details, width }: { details: Record<string, unknown>; width: number }) {
  const rows = learningDetailRows(details);
  if (rows.length === 0) {
    return <text><span fg={colors.text.disabled}>No extra review metadata</span></text>;
  }

  return (
    <box flexDirection="column">
      {rows.map((row, index) => (
        <text key={index}>
          <span fg={colors.text.muted}>{row.label} </span>
          <span fg={colors.text.disabled}>{truncateText(row.value, Math.max(8, width - row.label.length - 1))}</span>
        </text>
      ))}
    </box>
  );
}

function EvidenceList({ events, width }: { events: LearningEvent[]; width: number }) {
  if (events.length === 0) {
    return <text><span fg={colors.text.disabled}>No loaded evidence events</span></text>;
  }
  return (
    <box flexDirection="column">
      {events.slice(0, 5).map((event) => (
        <box key={event.id} flexDirection="column" marginBottom={1}>
          <text>
            <span fg={colors.text.secondary}>{event.source_type}</span>
            <span fg={colors.text.disabled}> / {event.scope}</span>
            <span fg={colors.text.disabled}> {"\u2502"} {truncateText(event.signal, width - 20)}</span>
          </text>
          {event.evidence_ids.length > 0 && (
            <text>
              <span fg={colors.text.muted}>  evidence </span>
              <span fg={colors.text.disabled}>
                {truncateText(summarizeLearningEvidence(event.evidence_ids), width - 11)}
              </span>
            </text>
          )}
        </box>
      ))}
      {events.length > 5 && (
        <text><span fg={colors.text.disabled}>... +{events.length - 5} events</span></text>
      )}
    </box>
  );
}

function CandidateDetails({
  candidate,
  events,
  width,
  height,
}: {
  candidate: LearningCandidate | null;
  events: LearningEvent[];
  width: number;
  height: number;
}) {
  const { accentValue } = useAccentColor();
  const textWidth = Math.max(10, width - 2);

  if (!candidate) {
    return <text><span fg={colors.text.muted}>No learning candidates. Press p to scan review sources.</span></text>;
  }

  const effect = learningCandidateEffect(candidate.change_type, candidate.status);

  return (
    <box flexDirection="column" width={width} height={height} paddingLeft={1} overflow="hidden">
      <text>
        <span fg={accentValue}>learning proposal</span>
        <span fg={colors.text.disabled}> {"\u2502"} </span>
        <span fg={statusColor(candidate.status, accentValue)}>{candidate.status}</span>
        <span fg={colors.text.disabled}> {"\u2502"} {formatTimeAgo(candidate.created_at)}</span>
      </text>

      <box marginTop={1} flexDirection="column">
        <text>
          <span fg={colors.text.muted}>type </span>
          <span fg={colors.text.secondary}>{learningChangeLabel(candidate.change_type)}</span>
        </text>
        <text>
          <span fg={colors.text.muted}>applies to </span>
          <span fg={colors.text.secondary}>{truncateText(candidate.target_key, textWidth - 8)}</span>
        </text>
        <text>
          <span fg={colors.text.muted}>policy </span>
          <span fg={colors.text.secondary}>{candidate.policy_version}</span>
        </text>
        {effect && (
          <text>
            <span fg={colors.text.muted}>effect </span>
            <span fg={colors.text.secondary}>{effect}</span>
          </text>
        )}
      </box>

      <box marginTop={1} flexDirection="column">
        <text><span fg={colors.text.muted}>PROPOSAL</span></text>
        <text><span fg={colors.text.secondary}>{truncateText(candidate.proposal, textWidth)}</span></text>
      </box>

      <box marginTop={1} flexDirection="column">
        <text><span fg={colors.text.muted}>RATIONALE</span></text>
        <text><span fg={colors.text.disabled}>{truncateText(cleanLearningText(candidate.rationale), textWidth)}</span></text>
      </box>

      {candidate.expected_metric && (
        <box marginTop={1} flexDirection="column">
          <text><span fg={colors.text.muted}>EXPECTED METRIC</span></text>
          <text><span fg={colors.text.disabled}>{truncateText(candidate.expected_metric, textWidth)}</span></text>
        </box>
      )}

      <box marginTop={2} flexDirection="column">
        <text><span fg={colors.text.muted}>EVIDENCE</span></text>
        <EvidenceList events={events} width={textWidth} />
      </box>

      <box marginTop={2} flexDirection="column">
        <text><span fg={colors.text.muted}>REVIEW METADATA</span></text>
        <DetailsSummary details={candidate.details} width={textWidth} />
      </box>
    </box>
  );
}

export function LearningSection({ tab, totalCount, height, width }: LearningSectionProps) {
  const { accentValue } = useAccentColor();
  const listWidth = Math.min(48, Math.max(32, Math.floor(width * 0.42)));
  const detailWidth = Math.max(0, width - listWidth - 1);

  const renderItem = (candidate: LearningCandidate, ctx: RenderItemContext) => {
    const textWidth = listWidth - 4;
    const tagColor = ctx.isSelected ? colors.text.secondary : colors.text.disabled;

    return (
      <box flexDirection="column" marginBottom={1}>
        <text>
          <span fg={ctx.colors.text}>{truncateText(candidate.proposal, textWidth)}</span>
        </text>
        <text>
          <span fg={statusColor(candidate.status, accentValue)}>{candidate.status}</span>
          <span fg={tagColor}> {learningChangeLabel(candidate.change_type)}</span>
          <span fg={tagColor}> [{shortTime(candidate.created_at)}]</span>
        </text>
      </box>
    );
  };

  return (
    <ListDetailSection
      items={tab.filteredCandidates}
      selectedIndex={tab.selectedIndex}
      renderItem={renderItem}
      getKey={(candidate) => candidate.id}
      emptyMessage="No learning candidates. Press p to scan review sources."
      searchQuery={tab.searchQuery}
      searchMode={tab.searchMode}
      focusPane={tab.focusPane}
      height={height}
      width={width}
      itemHeight={3}
      onItemClick={tab.setSelectedIndex}
      totalCount={totalCount}
      details={
        <CandidateDetails
          candidate={tab.selectedCandidate}
          events={tab.selectedEvents}
          width={detailWidth}
          height={height}
        />
      }
    />
  );
}
