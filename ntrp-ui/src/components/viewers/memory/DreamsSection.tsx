import type { Dream } from "../../../api/client.js";
import { colors, truncateText, type RenderItemContext } from "../../ui/index.js";
import { useAccentColor } from "../../../hooks/index.js";
import { shortTime } from "../../../lib/format.js";
import type { DreamsTabState } from "../../../hooks/useDreamsTab.js";
import { DreamDetailsView } from "./DreamDetailsView.js";
import { ListDetailSection, memoryDetailWidth } from "./ListDetailSection.js";

interface DreamsSectionProps {
  tab: DreamsTabState;
  height: number;
  width: number;
}

export function DreamsSection({ tab, height, width }: DreamsSectionProps) {
  const { accentValue } = useAccentColor();
  const listWidth = Math.min(45, Math.max(30, Math.floor(width * 0.4)));
  const detailWidth = memoryDetailWidth(width, listWidth);

  const renderItem = (dream: Dream, ctx: RenderItemContext) => {
    const textWidth = listWidth - 4;
    const tagColor = ctx.isSelected ? colors.text.secondary : colors.text.disabled;

    return (
      <box flexDirection="column" marginBottom={1}>
        <text>
          <span fg={ctx.colors.text}>{truncateText(dream.insight, textWidth)}</span>
        </text>
        <text>
          <span fg={ctx.isSelected ? accentValue : tagColor}>[{dream.bridge}]</span>
          <span fg={tagColor}> [{shortTime(dream.created_at)}]</span>
        </text>
      </box>
    );
  };

  return (
    <ListDetailSection
      items={tab.filteredDreams}
      selectedIndex={tab.selectedIndex}
      renderItem={renderItem}
      getKey={(d) => d.id}
      emptyMessage="No dreams generated yet"
      searchQuery={tab.searchQuery}
      searchMode={tab.searchMode}
      focusPane={tab.focusPane}
      height={height}
      width={width}
      itemHeight={3}
      onItemClick={tab.setSelectedIndex}
      details={
        <DreamDetailsView
          details={tab.dreamDetails}
          loading={tab.detailsLoading}
          width={detailWidth}
          height={height}
          isFocused={tab.focusPane === "details"}
          focusedSection={tab.detailSection}
          textExpanded={tab.textExpanded}
          textScrollOffset={tab.textScrollOffset}
          factsIndex={tab.factsIndex}
          confirmDelete={tab.confirmDelete}
        />
      }
    />
  );
}
