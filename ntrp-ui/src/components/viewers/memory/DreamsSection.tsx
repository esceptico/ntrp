import type { Dream, DreamDetails } from "../../../api/client.js";
import { colors, truncateText, type RenderItemContext } from "../../ui/index.js";
import { useAccentColor } from "../../../hooks/index.js";
import { formatTimeAgo } from "../../../lib/format.js";
import { DreamDetailsView, type DreamDetailSection } from "./DreamDetailsView.js";
import { ListDetailSection } from "./ListDetailSection.js";

interface DreamsSectionProps {
  dreams: Dream[];
  selectedIndex: number;
  dreamDetails: DreamDetails | null;
  detailsLoading: boolean;
  searchQuery: string;
  searchMode: boolean;
  focusPane: "list" | "details";
  height: number;
  width: number;
  detailSection: DreamDetailSection;
  textExpanded: boolean;
  textScrollOffset: number;
  factsIndex: number;
  confirmDelete: boolean;
}

function shortTime(iso: string): string {
  const full = formatTimeAgo(iso);
  return full.replace(" ago", "");
}

export function DreamsSection({
  dreams,
  selectedIndex,
  dreamDetails,
  detailsLoading,
  searchQuery,
  searchMode,
  focusPane,
  height,
  width,
  detailSection,
  textExpanded,
  textScrollOffset,
  factsIndex,
  confirmDelete,
}: DreamsSectionProps) {
  const { accentValue } = useAccentColor();
  const listWidth = Math.min(45, Math.max(30, Math.floor(width * 0.4)));
  const detailWidth = Math.max(0, width - listWidth - 1);

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
      items={dreams}
      selectedIndex={selectedIndex}
      renderItem={renderItem}
      getKey={(d) => d.id}
      emptyMessage="No dreams generated yet"
      searchQuery={searchQuery}
      searchMode={searchMode}
      focusPane={focusPane}
      height={height}
      width={width}
      itemHeight={3}
      details={
        <DreamDetailsView
          details={dreamDetails}
          loading={detailsLoading}
          width={detailWidth}
          height={height}
          isFocused={focusPane === "details"}
          focusedSection={detailSection}
          textExpanded={textExpanded}
          textScrollOffset={textScrollOffset}
          factsIndex={factsIndex}
          confirmDelete={confirmDelete}
        />
      }
    />
  );
}
