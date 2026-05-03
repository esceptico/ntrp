import type {
  Fact,
  MemoryAccessEvent,
  MemoryInjectionPolicyCandidate,
  MemoryInjectionPolicyPreview,
  MemoryInjectionPolicyReason,
  Observation,
} from "../../../api/client.js";
import { useAccentColor } from "../../../hooks/index.js";
import type { MemoryAccessTabState } from "../../../hooks/useMemoryAccessTab.js";
import { formatTimeAgo, shortTime } from "../../../lib/format.js";
import { memoryAccessSourceLabel } from "../../../lib/memoryAccess.js";
import { memoryMetadataRows } from "../../../lib/memoryMetadata.js";
import { colors, truncateText, type RenderItemContext } from "../../ui/index.js";
import { ListDetailSection, memoryDetailWidth } from "./ListDetailSection.js";
import { MemoryMetaLine, MemoryMetaRows } from "./MemoryMeta.js";

interface MemoryAccessSectionProps {
  tab: MemoryAccessTabState;
  totalCount: number;
  policyPreview: MemoryInjectionPolicyPreview | null;
  facts: Fact[];
  observations: Observation[];
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

function MetadataRows({ details, width }: { details: Record<string, unknown>; width: number }) {
  const rows = memoryMetadataRows(details);
  if (rows.length === 0) {
    return <text><span fg={colors.text.disabled}>No extra run metadata</span></text>;
  }
  return <MemoryMetaRows rows={rows.map((row) => ({ label: row.label.toLowerCase(), value: row.value }))} width={width} />;
}

function MemoryTextList<T>({
  title,
  ids,
  records,
  getText,
  width,
}: {
  title: string;
  ids: number[];
  records: Map<number, T>;
  getText: (record: T) => string;
  width: number;
}) {
  if (ids.length === 0) return null;

  const resolved = ids.flatMap((id) => {
    const record = records.get(id);
    return record ? [record] : [];
  });
  const visible = resolved.slice(0, 4);
  const missing = ids.length - resolved.length;
  const remaining = Math.max(0, resolved.length - visible.length);

  return (
    <box flexDirection="column" marginTop={1}>
      <text>
        <span fg={colors.text.muted}>{title} </span>
        <span fg={colors.text.secondary}>{ids.length}</span>
      </text>
      {visible.map((record, index) => (
        <text key={index}>
          <span fg={colors.text.disabled}>- {truncateText(getText(record), Math.max(8, width - 2))}</span>
        </text>
      ))}
      {(remaining > 0 || missing > 0) && (
        <text>
          <span fg={colors.text.disabled}>
            {remaining > 0 ? `... ${remaining} more loaded` : ""}
            {remaining > 0 && missing > 0 ? " / " : ""}
            {missing > 0 ? `${missing} not loaded here` : ""}
          </span>
        </text>
      )}
    </box>
  );
}

function AccessDetails({
  event,
  candidate,
  factsById,
  observationsById,
  width,
  height,
}: {
  event: MemoryAccessEvent | null;
  candidate: MemoryInjectionPolicyCandidate | null;
  factsById: Map<number, Fact>;
  observationsById: Map<number, Observation>;
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
      <MemoryMetaLine
        width={textWidth}
        segments={[
          { text: "sent memory", fg: accentValue },
          { text: memoryAccessSourceLabel(event.source), fg: colors.text.secondary },
          { text: formatTimeAgo(event.created_at), fg: colors.text.disabled },
        ]}
      />

      <box marginTop={1} flexDirection="column">
        <MemoryMetaRows
          width={textWidth}
          rows={[
            { label: "policy", value: event.policy_version, valueFg: colors.text.secondary },
            { label: "chars", value: event.formatted_chars, valueFg: colors.text.secondary },
            ...(event.query ? [{ label: "query", value: event.query, valueFg: colors.text.secondary }] : []),
          ]}
        />
      </box>

      <box marginTop={1} flexDirection="column">
        <MemoryMetaRows
          width={textWidth}
          rows={[
            { label: "retrieved", value: `${retrievedFacts} facts; ${retrievedPatterns} patterns`, valueFg: colors.text.secondary },
            { label: "injected", value: `${injectedFacts} facts; ${injectedPatterns} patterns`, valueFg: colors.text.secondary },
            ...(omittedFacts > 0 || omittedPatterns > 0
              ? [{ label: "omitted", value: `${omittedFacts} facts; ${omittedPatterns} patterns`, valueFg: colors.text.secondary }]
              : []),
          ]}
        />
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

      <MemoryTextList
        title="injected facts"
        ids={event.injected_fact_ids}
        records={factsById}
        getText={(fact) => fact.text}
        width={textWidth}
      />
      <MemoryTextList
        title="injected patterns"
        ids={event.injected_observation_ids}
        records={observationsById}
        getText={(observation) => observation.summary}
        width={textWidth}
      />
      <MemoryTextList
        title="bundled facts"
        ids={event.bundled_fact_ids}
        records={factsById}
        getText={(fact) => fact.text}
        width={textWidth}
      />
      <MemoryTextList
        title="omitted facts"
        ids={event.omitted_fact_ids}
        records={factsById}
        getText={(fact) => fact.text}
        width={textWidth}
      />
      <MemoryTextList
        title="omitted patterns"
        ids={event.omitted_observation_ids}
        records={observationsById}
        getText={(observation) => observation.summary}
        width={textWidth}
      />

      <box marginTop={2} flexDirection="column">
        <text><span fg={colors.text.muted}>RUN METADATA</span></text>
        <MetadataRows details={event.details} width={textWidth} />
      </box>
    </box>
  );
}

export function MemoryAccessSection({ tab, totalCount, policyPreview, facts, observations, height, width }: MemoryAccessSectionProps) {
  const { accentValue } = useAccentColor();
  const listWidth = Math.min(48, Math.max(32, Math.floor(width * 0.42)));
  const detailWidth = memoryDetailWidth(width, listWidth);
  const factsById = new Map(facts.map((fact) => [fact.id, fact]));
  const observationsById = new Map(observations.map((observation) => [observation.id, observation]));
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
      listWidth={listWidth}
      itemHeight={3}
      onItemClick={tab.setSelectedIndex}
      totalCount={totalCount}
      details={
        <AccessDetails
          event={tab.selectedEvent}
          candidate={tab.selectedEvent ? candidatesByEventId.get(tab.selectedEvent.id) ?? null : null}
          factsById={factsById}
          observationsById={observationsById}
          width={detailWidth}
          height={height}
        />
      }
    />
  );
}
