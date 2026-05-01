import type { MemoryEvent } from "../../../api/client.js";
import { useAccentColor } from "../../../hooks/index.js";
import type { MemoryEventsTabState } from "../../../hooks/useMemoryEventsTab.js";
import { formatTimeAgo, shortTime } from "../../../lib/format.js";
import { memoryMetadataRows } from "../../../lib/memoryMetadata.js";
import { colors, truncateText, type RenderItemContext } from "../../ui/index.js";
import { ListDetailSection } from "./ListDetailSection.js";

interface MemoryEventsSectionProps {
  tab: MemoryEventsTabState;
  totalCount: number;
  height: number;
  width: number;
}

function eventTarget(event: MemoryEvent): string {
  return event.target_id === null ? event.target_type : `${event.target_type} record`;
}

function MetadataRows({ details, width }: { details: Record<string, unknown>; width: number }) {
  const rows = memoryMetadataRows(details);
  if (rows.length === 0) {
    return <text><span fg={colors.text.disabled}>No extra audit metadata</span></text>;
  }
  return (
    <box flexDirection="column">
      {rows.map((row, index) => (
        <text key={index}>
          <span fg={colors.text.muted}>{row.label.toLowerCase()} </span>
          <span fg={colors.text.disabled}>{truncateText(row.value, Math.max(8, width - row.label.length - 1))}</span>
        </text>
      ))}
    </box>
  );
}

function EventDetails({
  event,
  width,
  height,
}: {
  event: MemoryEvent | null;
  width: number;
  height: number;
}) {
  const { accentValue } = useAccentColor();
  const textWidth = Math.max(10, width - 2);

  if (!event) {
    return <text><span fg={colors.text.muted}>No log entries</span></text>;
  }

  return (
    <box flexDirection="column" width={width} height={height} paddingLeft={1} overflow="hidden">
      <text>
        <span fg={accentValue}>audit event</span>
        <span fg={colors.text.disabled}> {"\u2502"} </span>
        <span fg={colors.text.secondary}>{event.action}</span>
        <span fg={colors.text.disabled}> {"\u2502"} {event.actor}</span>
        <span fg={colors.text.disabled}> {"\u2502"} {formatTimeAgo(event.created_at)}</span>
      </text>

      <box marginTop={1} flexDirection="column">
        <text>
          <span fg={colors.text.muted}>target </span>
          <span fg={colors.text.secondary}>{eventTarget(event)}</span>
        </text>
        <text>
          <span fg={colors.text.muted}>policy </span>
          <span fg={colors.text.secondary}>{event.policy_version}</span>
        </text>
        {event.source_type && (
          <text>
            <span fg={colors.text.muted}>source </span>
            <span fg={colors.text.secondary}>{event.source_type}</span>
            {event.source_ref && <span fg={colors.text.disabled}> {"\u2502"} {truncateText(event.source_ref, textWidth - 16)}</span>}
          </text>
        )}
      </box>

      {event.reason && (
        <box marginTop={1}>
          <text>
            <span fg={colors.text.muted}>reason </span>
            <span fg={colors.text.secondary}>{truncateText(event.reason, textWidth - 8)}</span>
          </text>
        </box>
      )}

      <box marginTop={2} flexDirection="column">
        <text><span fg={colors.text.muted}>AUDIT METADATA</span></text>
        <MetadataRows details={event.details} width={textWidth} />
      </box>
    </box>
  );
}

export function MemoryEventsSection({ tab, totalCount, height, width }: MemoryEventsSectionProps) {
  const { accentValue } = useAccentColor();
  const listWidth = Math.min(45, Math.max(30, Math.floor(width * 0.4)));
  const detailWidth = Math.max(0, width - listWidth - 1);

  const renderItem = (event: MemoryEvent, ctx: RenderItemContext) => {
    const textWidth = listWidth - 4;
    const tagColor = ctx.isSelected ? colors.text.secondary : colors.text.disabled;

    return (
      <box flexDirection="column" marginBottom={1}>
        <text>
          <span fg={ctx.colors.text}>{truncateText(event.action, textWidth)}</span>
        </text>
        <text>
          <span fg={ctx.isSelected ? accentValue : tagColor}>{event.actor}</span>
          <span fg={tagColor}> {eventTarget(event)}</span>
          <span fg={tagColor}> [{shortTime(event.created_at)}]</span>
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
      emptyMessage="No log entries"
      searchQuery={tab.searchQuery}
      searchMode={tab.searchMode}
      focusPane={tab.focusPane}
      height={height}
      width={width}
      itemHeight={3}
      onItemClick={tab.setSelectedIndex}
      totalCount={totalCount}
      details={<EventDetails event={tab.selectedEvent} width={detailWidth} height={height} />}
    />
  );
}
