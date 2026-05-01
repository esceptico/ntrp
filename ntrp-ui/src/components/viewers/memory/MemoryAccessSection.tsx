import type {
  MemoryAccessEvent,
  MemoryInjectionPolicyCandidate,
  MemoryInjectionPolicyPreview,
  MemoryInjectionPolicyReason,
} from "../../../api/client.js";
import { useAccentColor } from "../../../hooks/index.js";
import type { MemoryAccessTabState } from "../../../hooks/useMemoryAccessTab.js";
import { formatTimeAgo, shortTime } from "../../../lib/format.js";
import { memoryAccessSourceLabel } from "../../../lib/memoryAccess.js";
import { colors, truncateText, type RenderItemContext } from "../../ui/index.js";
import { ListDetailSection } from "./ListDetailSection.js";

interface MemoryAccessSectionProps {
  tab: MemoryAccessTabState;
  totalCount: number;
  policyPreview: MemoryInjectionPolicyPreview | null;
  height: number;
  width: number;
}

const REASON_LABELS: Record<MemoryInjectionPolicyReason, string> = {
  empty_recall: "empty recall",
  over_budget: "over budget",
  pattern_heavy: "pattern-heavy",
};

function reasonLabel(reason: MemoryInjectionPolicyReason): string {
  return REASON_LABELS[reason] ?? reason;
}

function reasonsLabel(reasons: MemoryInjectionPolicyReason[]): string {
  return reasons.map(reasonLabel).join(", ");
}

function idsLabel(ids: number[], width: number): string {
  if (ids.length === 0) return "none";
  return truncateText(ids.map((id) => `#${id}`).join(" "), width);
}

function DetailsJson({ details, width }: { details: Record<string, unknown>; width: number }) {
  const lines = JSON.stringify(details, null, 2).split("\n");
  const visible = lines.slice(0, 10);
  return (
    <box flexDirection="column">
      {visible.map((line, index) => (
        <text key={index}>
          <span fg={colors.text.disabled}>{truncateText(line, width)}</span>
        </text>
      ))}
      {lines.length > visible.length && (
        <text><span fg={colors.text.disabled}>... +{lines.length - visible.length} lines</span></text>
      )}
    </box>
  );
}

function AccessDetails({
  event,
  candidate,
  width,
  height,
}: {
  event: MemoryAccessEvent | null;
  candidate: MemoryInjectionPolicyCandidate | null;
  width: number;
  height: number;
}) {
  const { accentValue } = useAccentColor();
  const textWidth = Math.max(10, width - 2);

  if (!event) {
    return <text><span fg={colors.text.muted}>No sent-memory records</span></text>;
  }

  const retrievedFacts = event.retrieved_fact_ids.length;
  const retrievedPatterns = event.retrieved_observation_ids.length;
  const injectedFacts = event.injected_fact_ids.length;
  const injectedPatterns = event.injected_observation_ids.length;
  const omittedFacts = event.omitted_fact_ids.length;
  const omittedPatterns = event.omitted_observation_ids.length;

  return (
    <box flexDirection="column" width={width} height={height} paddingLeft={1} overflow="hidden">
      <text>
        <span fg={accentValue}>sent #{event.id}</span>
        <span fg={colors.text.disabled}> {"\u2502"} </span>
        <span fg={colors.text.secondary}>{memoryAccessSourceLabel(event.source)}</span>
        <span fg={colors.text.disabled}> {"\u2502"} {formatTimeAgo(event.created_at)}</span>
      </text>

      <box marginTop={1} flexDirection="column">
        <text>
          <span fg={colors.text.muted}>policy </span>
          <span fg={colors.text.secondary}>{event.policy_version}</span>
        </text>
        <text>
          <span fg={colors.text.muted}>chars </span>
          <span fg={colors.text.secondary}>{event.formatted_chars}</span>
        </text>
        {event.query && (
          <text>
            <span fg={colors.text.muted}>query </span>
            <span fg={colors.text.secondary}>{truncateText(event.query, textWidth - 7)}</span>
          </text>
        )}
      </box>

      <box marginTop={1} flexDirection="column">
        <text>
          <span fg={colors.text.muted}>retrieved </span>
          <span fg={colors.text.secondary}>{retrievedFacts} facts</span>
          <span fg={colors.text.disabled}> / </span>
          <span fg={colors.text.secondary}>{retrievedPatterns} patterns</span>
        </text>
        <text>
          <span fg={colors.text.muted}>injected  </span>
          <span fg={colors.text.secondary}>{injectedFacts} facts</span>
          <span fg={colors.text.disabled}> / </span>
          <span fg={colors.text.secondary}>{injectedPatterns} patterns</span>
        </text>
        {(omittedFacts > 0 || omittedPatterns > 0) && (
          <text>
            <span fg={colors.text.muted}>omitted   </span>
            <span fg={colors.text.secondary}>{omittedFacts} facts</span>
            <span fg={colors.text.disabled}> / </span>
            <span fg={colors.text.secondary}>{omittedPatterns} patterns</span>
          </text>
        )}
      </box>

      {candidate && (
        <box marginTop={1} flexDirection="column">
          <text>
            <span fg={accentValue}>policy flag </span>
            <span fg={colors.text.secondary}>{reasonsLabel(candidate.reasons)}</span>
          </text>
          <text>
            <span fg={colors.text.muted}>next </span>
            <span fg={colors.text.disabled}>{truncateText(candidate.recommendation, textWidth - 5)}</span>
          </text>
        </box>
      )}

      <box marginTop={1} flexDirection="column">
        <text>
          <span fg={colors.text.muted}>fact ids </span>
          <span fg={colors.text.disabled}>{idsLabel(event.injected_fact_ids, textWidth - 9)}</span>
        </text>
        <text>
          <span fg={colors.text.muted}>pattern ids </span>
          <span fg={colors.text.disabled}>{idsLabel(event.injected_observation_ids, textWidth - 12)}</span>
        </text>
        {event.bundled_fact_ids.length > 0 && (
          <text>
            <span fg={colors.text.muted}>bundled </span>
            <span fg={colors.text.disabled}>{idsLabel(event.bundled_fact_ids, textWidth - 9)}</span>
          </text>
        )}
      </box>

      <box marginTop={2} flexDirection="column">
        <text><span fg={colors.text.muted}>DETAILS</span></text>
        <DetailsJson details={event.details} width={textWidth} />
      </box>
    </box>
  );
}

export function MemoryAccessSection({ tab, totalCount, policyPreview, height, width }: MemoryAccessSectionProps) {
  const { accentValue } = useAccentColor();
  const listWidth = Math.min(48, Math.max(32, Math.floor(width * 0.42)));
  const detailWidth = Math.max(0, width - listWidth - 1);
  const candidatesByEventId = new Map(
    (policyPreview?.candidates ?? []).map((candidate) => [candidate.access_event_id, candidate])
  );

  const renderItem = (event: MemoryAccessEvent, ctx: RenderItemContext) => {
    const textWidth = listWidth - 4;
    const tagColor = ctx.isSelected ? colors.text.secondary : colors.text.disabled;
    const query = event.query ? truncateText(event.query, textWidth) : "prompt context";
    const injected = `${event.injected_fact_ids.length}f/${event.injected_observation_ids.length}p`;
    const sourceLabel = memoryAccessSourceLabel(event.source);
    const createdAt = shortTime(event.created_at);
    const flagWidth = Math.max(0, textWidth - sourceLabel.length - injected.length - createdAt.length - 6);
    const candidate = candidatesByEventId.get(event.id);
    const flag = candidate && flagWidth > 4 ? ` ! ${truncateText(reasonsLabel(candidate.reasons), flagWidth - 3)}` : "";

    return (
      <box flexDirection="column" marginBottom={1}>
        <text>
          <span fg={ctx.colors.text}>{query}</span>
        </text>
        <text>
          <span fg={ctx.isSelected ? accentValue : tagColor}>{sourceLabel}</span>
          <span fg={tagColor}> {injected}</span>
          <span fg={tagColor}> [{createdAt}]</span>
          {flag && <span fg={ctx.isSelected ? accentValue : colors.status.warning}>{flag}</span>}
        </text>
      </box>
    );
  };

  return (
    <ListDetailSection
      items={tab.filteredEvents}
      selectedIndex={tab.selectedIndex}
      renderItem={renderItem}
      getKey={(event) => event.id}
      emptyMessage="No sent-memory records"
      searchQuery={tab.searchQuery}
      searchMode={tab.searchMode}
      focusPane={tab.focusPane}
      height={height}
      width={width}
      itemHeight={3}
      onItemClick={tab.setSelectedIndex}
      totalCount={totalCount}
      details={
        <AccessDetails
          event={tab.selectedEvent}
          candidate={tab.selectedEvent ? candidatesByEventId.get(tab.selectedEvent.id) ?? null : null}
          width={detailWidth}
          height={height}
        />
      }
    />
  );
}
