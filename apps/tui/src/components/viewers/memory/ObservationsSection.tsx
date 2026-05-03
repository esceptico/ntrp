import type { Observation } from "../../../api/client.js";
import { colors, truncateText, type RenderItemContext } from "../../ui/index.js";
import { useAccentColor } from "../../../hooks/index.js";
import { shortTime } from "../../../lib/format.js";
import type { ObservationsTabState } from "../../../hooks/useObservationsTab.js";
import { ObservationDetailsView } from "./ObservationDetailsView.js";
import { ListDetailSection, memoryDetailWidth } from "./ListDetailSection.js";

interface ObservationsSectionProps {
  tab: ObservationsTabState;
  height: number;
  width: number;
  saving: boolean;
}

function patternProducerLabel(obs: Observation): string {
  const createdBy = obs.created_by || "legacy";
  switch (createdBy) {
    case "consolidation":
      return "auto";
    case "temporal":
      return "temporal";
    case "manual":
      return "manual";
    case "legacy":
      return "legacy";
    default:
      return createdBy;
  }
}

export function ObservationsSection({ tab, height, width, saving }: ObservationsSectionProps) {
  const { accentValue } = useAccentColor();
  const listWidth = Math.min(45, Math.max(30, Math.floor(width * 0.4)));
  const detailWidth = memoryDetailWidth(width, listWidth);

  const renderItem = (obs: Observation, ctx: RenderItemContext) => {
    const textWidth = listWidth - 4;
    const tagColor = ctx.isSelected ? colors.text.secondary : colors.text.disabled;

    return (
      <box flexDirection="column" marginBottom={1}>
        <text>
          <span fg={ctx.colors.text}>{truncateText(obs.summary, textWidth)}</span>
        </text>
        <text>
          <span fg={ctx.isSelected ? accentValue : tagColor}>{obs.evidence_count} facts</span>
          <span fg={tagColor}> · used {obs.access_count}</span>
          <span fg={tagColor}> · {patternProducerLabel(obs)}</span>
          <span fg={tagColor}> · {shortTime(obs.created_at)}</span>
          {obs.archived_at && <span fg={colors.status.error}> archived</span>}
        </text>
      </box>
    );
  };

  return (
    <ListDetailSection
      items={tab.filteredObservations}
      selectedIndex={tab.selectedIndex}
      renderItem={renderItem}
      getKey={(o) => o.id}
      emptyMessage="No patterns synthesized yet"
      searchQuery={tab.searchQuery}
      searchMode={tab.searchMode}
      focusPane={tab.focusPane}
      height={height}
      width={width}
      itemHeight={3}
      onItemClick={tab.setSelectedIndex}
      details={
        <ObservationDetailsView
          details={tab.obsDetails}
          loading={tab.detailsLoading}
          width={detailWidth}
          height={height}
          isFocused={tab.focusPane === "details"}
          focusedSection={tab.detailSection}
          textExpanded={tab.textExpanded}
          textScrollOffset={tab.textScrollOffset}
          factsIndex={tab.factsIndex}
          editMode={tab.editMode}
          editText={tab.editText}
          cursorPos={tab.cursorPos}
          setEditText={tab.setEditText}
          setCursorPos={tab.setCursorPos}
          confirmDelete={tab.confirmDelete}
          saving={saving}
        />
      }
    />
  );
}
