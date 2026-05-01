import type { LearningCandidate, LearningEvent } from "../../../api/client.js";
import { useAccentColor } from "../../../hooks/index.js";
import type { LearningTabState } from "../../../hooks/useLearningTab.js";
import { formatTimeAgo, shortTime } from "../../../lib/format.js";
import { cleanLearningText, learningDetailRows, summarizeLearningEvidence } from "../../../lib/memoryLearningDetails.js";
import {
  canApplyLearningCandidate,
  canApproveLearningCandidate,
  canRejectLearningCandidate,
  canRevertLearningCandidate,
  learningCandidateIsActive,
  learningChangeLabel,
  learningLane,
  learningLaneLabel,
  learningTargetLabel,
} from "../../../lib/memoryLearning.js";
import { colors, truncateText, type RenderItemContext } from "../../ui/index.js";
import { ListDetailSection, memoryDetailWidth } from "./ListDetailSection.js";

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

function laneColor(lane: string, accent: string): string {
  switch (lane) {
    case "runtime":
      return accent;
    case "skill":
      return colors.status.success;
    case "automation":
      return colors.status.warning;
    default:
      return colors.text.secondary;
  }
}

function DetailsSummary({ details, width }: { details: Record<string, unknown>; width: number }) {
  const rows = learningDetailRows(details);
  if (rows.length === 0) {
    return null;
  }

  return (
    <box marginTop={2} flexDirection="column">
      <text><span fg={colors.text.muted}>Source summary</span></text>
      {rows.map((row, index) => (
        <text key={index}>
          <span fg={colors.text.muted}>{row.label} </span>
          <span fg={colors.text.disabled}>{truncateText(row.value, Math.max(8, width - row.label.length - 1))}</span>
        </text>
      ))}
    </box>
  );
}

function evidenceSourceLabel(event: LearningEvent): string {
  const source = event.source_type.replaceAll("_", " ");
  if (event.scope && event.scope !== event.source_type) return `${source} / ${event.scope}`;
  return source;
}

function EvidenceList({ events, width }: { events: LearningEvent[]; width: number }) {
  if (events.length === 0) {
    return <text><span fg={colors.text.disabled}>No evidence loaded for this proposal.</span></text>;
  }
  return (
    <box flexDirection="column">
      {events.slice(0, 4).map((event) => (
        <box key={event.id} flexDirection="column" marginBottom={1}>
          <text>
            <span fg={colors.text.secondary}>{evidenceSourceLabel(event)}</span>
            <span fg={colors.text.disabled}> {"\u2502"} {truncateText(cleanLearningText(event.signal), width - 20)}</span>
          </text>
          {event.evidence_ids.length > 0 && (
            <text>
              <span fg={colors.text.muted}>  based on </span>
              <span fg={colors.text.disabled}>
                {truncateText(summarizeLearningEvidence(event.evidence_ids), width - 11)}
              </span>
            </text>
          )}
        </box>
      ))}
      {events.length > 4 && (
        <text><span fg={colors.text.disabled}>... +{events.length - 4} more evidence events</span></text>
      )}
    </box>
  );
}

function primaryEvidenceText(candidate: LearningCandidate, events: LearningEvent[]): string {
  const signal = events.find((event) => event.signal.trim())?.signal;
  return cleanLearningText(signal || candidate.proposal);
}

function proposalTitle(candidate: LearningCandidate, events: LearningEvent[]): string {
  const lane = learningLane(candidate.change_type, candidate.target_key);
  if (lane === "automation") return "Automation issue needs review";
  if (candidate.change_type === "prune_rule") return "Cleanup rule needs review";
  if (candidate.change_type === "profile_rule") return "Profile memory needs review";
  if (candidate.change_type === "supersession_review") return "Profile conflict needs review";
  if (candidate.target_key.includes("injection")) return "Sent memory behavior needs review";
  if (candidate.target_key.includes("recall")) return "Memory search behavior needs review";
  if (candidate.target_key.includes("compression")) return "Pattern compression needs review";
  if (lane === "skill") return "Skill idea needs review";
  if (lane === "runtime") return "Prompt behavior needs review";
  if (events.length > 0) return "Memory behavior needs review";
  return "Learning proposal needs review";
}

function stateLabel(candidate: LearningCandidate): string {
  if (candidate.status === "proposed") return "Needs decision";
  if (candidate.status === "approved" && learningCandidateIsActive(candidate)) return "Active in prompts";
  if (candidate.status === "approved") return "Ready to apply";
  if (candidate.status === "applied") return "Active";
  if (candidate.status === "reverted") return "Reverted";
  if (candidate.status === "rejected") return "Rejected";
  return candidate.status;
}

function actionText(candidate: LearningCandidate): string {
  const lane = learningLane(candidate.change_type, candidate.target_key);
  if (canApproveLearningCandidate(candidate.status)) {
    if (lane === "runtime" || lane === "skill") {
      return "Approve to let future prompts use this note, or reject it if it is not useful.";
    }
    return "Approve if this should become a durable improvement candidate. Reject it if the evidence is weak.";
  }
  if (canApplyLearningCandidate(candidate.status)) {
    if (lane === "memory") return "Apply to make memory extraction, recall, or cleanup prompts use this note.";
    if (lane === "automation") return "Apply to make matching future automation runs use this note.";
    return "Apply to mark this prompt note as fully handled.";
  }
  if (canRevertLearningCandidate(candidate.status)) {
    return "This is active now. Revert it if it is making behavior worse.";
  }
  if (canRejectLearningCandidate(candidate.status)) {
    return "Reject if this should not affect future behavior.";
  }
  return "No action is needed for this item.";
}

function impactText(candidate: LearningCandidate): string {
  const lane = learningLane(candidate.change_type, candidate.target_key);
  if (lane === "automation") {
    return candidate.status === "applied"
      ? "Matching automation runs already receive this note before they run."
      : "If applied, matching automation runs will receive this note before they run.";
  }
  if (lane === "memory") {
    return candidate.status === "applied"
      ? "Memory extraction, recall, or cleanup already uses this policy note."
      : "If applied, memory extraction, recall, or cleanup will use this policy note.";
  }
  if (lane === "skill") {
    return "If approved, future prompts can use this skill note.";
  }
  return "If approved, future prompts can use this runtime note.";
}

function actionHint(candidate: LearningCandidate): string {
  const parts: string[] = [];
  if (canApproveLearningCandidate(candidate.status)) parts.push("a approve");
  if (canApplyLearningCandidate(candidate.status)) parts.push("a apply");
  if (canRejectLearningCandidate(candidate.status)) parts.push("d reject");
  if (canRevertLearningCandidate(candidate.status)) parts.push("z revert");
  return parts.join("  ");
}

function CandidateDetails({
  candidate,
  events,
  confirmStatus,
  confirmProposalScan,
  width,
  height,
}: {
  candidate: LearningCandidate | null;
  events: LearningEvent[];
  confirmStatus: "approved" | "applied" | "rejected" | "reverted" | null;
  confirmProposalScan: boolean;
  width: number;
  height: number;
}) {
  const { accentValue } = useAccentColor();
  const textWidth = Math.max(10, width - 2);

  if (!candidate && !confirmProposalScan) {
    return <text><span fg={colors.text.muted}>No learning inbox items. Press p to scan review sources.</span></text>;
  }
  if (!candidate) {
    return (
      <box flexDirection="column" width={width} height={height} paddingLeft={1} overflow="hidden">
        <text><span fg={colors.status.warning}>create new learning proposals from review sources?</span></text>
        <text><span fg={colors.text.disabled}>press y to confirm, n or esc to cancel</span></text>
      </box>
    );
  }

  const lane = learningLane(candidate.change_type, candidate.target_key);
  const title = proposalTitle(candidate, events);
  const action = actionText(candidate);
  const hint = actionHint(candidate);

  return (
    <box flexDirection="column" width={width} height={height} paddingLeft={1} overflow="hidden">
      <text>
        <span fg={accentValue}>{title}</span>
        <span fg={colors.text.disabled}> {"\u2502"} </span>
        <span fg={laneColor(lane, accentValue)}>{learningLaneLabel(lane)}</span>
        <span fg={colors.text.disabled}> {"\u2502"} </span>
        <span fg={statusColor(candidate.status, accentValue)}>{stateLabel(candidate)}</span>
        <span fg={colors.text.disabled}> {"\u2502"} {formatTimeAgo(candidate.created_at)}</span>
      </text>

      <box marginTop={1} flexDirection="column">
        <text>
          <span fg={colors.text.muted}>What happened</span>
        </text>
        <text>
          <span fg={colors.text.secondary}>{truncateText(primaryEvidenceText(candidate, events), textWidth)}</span>
        </text>
      </box>

      <box marginTop={1} flexDirection="column">
        <text>
          <span fg={colors.text.muted}>What would change</span>
        </text>
        <text>
          <span fg={colors.text.secondary}>{truncateText(learningTargetLabel(candidate.target_key), textWidth)}</span>
        </text>
        <text>
          <span fg={colors.text.disabled}>{truncateText(impactText(candidate), textWidth)}</span>
        </text>
      </box>

      <box marginTop={1} flexDirection="column">
        <text><span fg={colors.text.muted}>What you can do</span></text>
        <text><span fg={colors.text.secondary}>{truncateText(action, textWidth)}</span></text>
        {hint && (
          <text>
            <span fg={colors.text.disabled}>{hint}</span>
          </text>
        )}
      </box>

      {(confirmStatus || confirmProposalScan) && (
        <box marginTop={1} flexDirection="column">
          <text>
            <span fg={colors.status.warning}>
              {confirmProposalScan
                ? "create new learning proposals from review sources?"
                : confirmStatus === "approved"
                  ? "approve this proposal?"
                  : confirmStatus === "applied"
                    ? "apply this proposal?"
                    : confirmStatus === "reverted"
                      ? "revert this applied proposal?"
                      : "reject this proposal?"}
            </span>
          </text>
          <text><span fg={colors.text.disabled}>press y to confirm, n or esc to cancel</span></text>
        </box>
      )}

      <box marginTop={1} flexDirection="column">
        <text><span fg={colors.text.muted}>Proposed note</span></text>
        <text><span fg={colors.text.secondary}>{truncateText(candidate.proposal, textWidth)}</span></text>
      </box>

      <box marginTop={1} flexDirection="column">
        <text><span fg={colors.text.muted}>Why ntrp proposed it</span></text>
        <text><span fg={colors.text.disabled}>{truncateText(cleanLearningText(candidate.rationale), textWidth)}</span></text>
      </box>

      {candidate.expected_metric && (
        <box marginTop={1} flexDirection="column">
          <text><span fg={colors.text.muted}>Success would look like</span></text>
          <text><span fg={colors.text.disabled}>{truncateText(candidate.expected_metric, textWidth)}</span></text>
        </box>
      )}

      <box marginTop={2} flexDirection="column">
        <text><span fg={colors.text.muted}>Evidence</span></text>
        <EvidenceList events={events} width={textWidth} />
      </box>

      <DetailsSummary details={candidate.details} width={textWidth} />
    </box>
  );
}

export function LearningSection({ tab, totalCount, height, width }: LearningSectionProps) {
  const { accentValue } = useAccentColor();
  const listWidth = Math.min(48, Math.max(32, Math.floor(width * 0.42)));
  const detailWidth = memoryDetailWidth(width, listWidth);

  const renderItem = (candidate: LearningCandidate, ctx: RenderItemContext) => {
    const textWidth = listWidth - 4;
    const tagColor = ctx.isSelected ? colors.text.secondary : colors.text.disabled;
    const lane = learningLane(candidate.change_type, candidate.target_key);
    const title = proposalTitle(candidate, []);

    return (
      <box flexDirection="column" marginBottom={1}>
        <text>
          <span fg={ctx.colors.text}>{truncateText(title, textWidth)}</span>
        </text>
        <text>
          <span fg={laneColor(lane, accentValue)}>{learningLaneLabel(lane)}</span>
          <span fg={tagColor}> {"\u2502"} </span>
          <span fg={statusColor(candidate.status, accentValue)}>{stateLabel(candidate)}</span>
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
      emptyMessage="No learning candidates. Press p to create proposals from review sources."
      searchQuery={tab.searchQuery}
      searchMode={tab.searchMode}
      focusPane={tab.focusPane}
      height={height}
      width={width}
      listWidth={listWidth}
      itemHeight={3}
      onItemClick={tab.setSelectedIndex}
      totalCount={totalCount}
      details={
        <CandidateDetails
          candidate={tab.selectedCandidate}
          events={tab.selectedEvents}
          confirmStatus={tab.confirmStatus}
          confirmProposalScan={tab.confirmProposalScan}
          width={detailWidth}
          height={height}
        />
      }
    />
  );
}
