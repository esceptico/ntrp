import type { MemoryEvent } from "../../../api/client.js";
import { useAccentColor } from "../../../hooks/index.js";
import type { MemoryEventsTabState } from "../../../hooks/useMemoryEventsTab.js";
import { formatTimeAgo, shortTime } from "../../../lib/format.js";
import { memoryMetadataRows } from "../../../lib/memoryMetadata.js";
import { colors, truncateText, type RenderItemContext } from "../../ui/index.js";
import { ListDetailSection, memoryDetailWidth } from "./ListDetailSection.js";
import { MemoryMetaLine, MemoryMetaRows } from "./MemoryMeta.js";

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
  return <MemoryMetaRows rows={rows.map((row) => ({ label: row.label.toLowerCase(), value: row.value }))} width={width} />;
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
      <MemoryMetaLine
        width={textWidth}
        segments={[
          { text: "audit event", fg: accentValue },
          { text: event.action, fg: colors.text.secondary },
          { text: event.actor, fg: colors.text.disabled },
          { text: formatTimeAgo(event.created_at), fg: colors.text.disabled },
        ]}
      />

      <box marginTop={1} flexDirection="column">
        <MemoryMetaRows
          width={textWidth}
          rows={[
            { label: "target", value: eventTarget(event), valueFg: colors.text.secondary },
            { label: "policy", value: event.policy_version, valueFg: colors.text.secondary },
            ...(event.source_type
              ? [{
                label: "source",
                value: event.source_ref ? `${event.source_type}; ${event.source_ref}` : event.source_type,
                valueFg: colors.text.secondary,
              }]
              : []),
          ]}
        />
      </box>

      {event.reason && (
        <box marginTop={1}>
          <MemoryMetaRows
            width={textWidth}
            rows={[{ label: "reason", value: event.reason, valueFg: colors.text.secondary }]}
          />
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
  const detailWidth = memoryDetailWidth(width, listWidth);

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
