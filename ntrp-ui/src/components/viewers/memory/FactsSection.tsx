import type { Fact, FactDetails } from "../../../api/client.js";
import { colors, truncateText, type RenderItemContext } from "../../ui/index.js";
import { useAccentColor } from "../../../hooks/index.js";
import { formatTimeAgo } from "../../../lib/format.js";
import { FactDetailsView, type FactDetailSection } from "./FactDetailsView.js";
import { ListDetailSection } from "./ListDetailSection.js";

interface FactsSectionProps {
  facts: Fact[];
  selectedIndex: number;
  factDetails: FactDetails | null;
  detailsLoading: boolean;
  searchQuery: string;
  searchMode: boolean;
  focusPane: "list" | "details";
  height: number;
  width: number;
  detailSection: FactDetailSection;
  textExpanded: boolean;
  textScrollOffset: number;
  entitiesIndex: number;
  linkedIndex: number;
  editMode: boolean;
  editText: string;
  cursorPos: number;
  setEditText: (text: string | ((prev: string) => string)) => void;
  setCursorPos: (pos: number | ((prev: number) => number)) => void;
  confirmDelete: boolean;
  saving: boolean;
}

function shortTime(iso: string): string {
  const full = formatTimeAgo(iso);
  return full.replace(" ago", "");
}

export function FactsSection({
  facts,
  selectedIndex,
  factDetails,
  detailsLoading,
  searchQuery,
  searchMode,
  focusPane,
  height,
  width,
  detailSection,
  textExpanded,
  textScrollOffset,
  entitiesIndex,
  linkedIndex,
  editMode,
  editText,
  cursorPos,
  setEditText,
  setCursorPos,
  confirmDelete,
  saving,
}: FactsSectionProps) {
  const { accentValue } = useAccentColor();
  const listWidth = Math.min(45, Math.max(30, Math.floor(width * 0.4)));
  const detailWidth = Math.max(0, width - listWidth - 1);

  const renderItem = (fact: Fact, ctx: RenderItemContext) => {
    const textWidth = listWidth - 4;
    const typeTag = fact.fact_type === "world" ? "world" : "exp";
    const typeColor = fact.fact_type === "world" ? colors.status.warning : accentValue;
    const tagColor = ctx.isSelected ? colors.text.secondary : colors.text.disabled;

    return (
      <box flexDirection="column" marginBottom={1}>
        <text>
          <span fg={ctx.colors.text}>{truncateText(fact.text, textWidth)}</span>
        </text>
        <text>
          <span fg={ctx.isSelected ? typeColor : tagColor}>[{typeTag}]</span>
          <span fg={tagColor}> [{fact.source_type}] [{shortTime(fact.created_at)}]</span>
        </text>
      </box>
    );
  };

  return (
    <ListDetailSection
      items={facts}
      selectedIndex={selectedIndex}
      renderItem={renderItem}
      getKey={(f) => f.id}
      emptyMessage="No facts stored yet"
      searchQuery={searchQuery}
      searchMode={searchMode}
      focusPane={focusPane}
      height={height}
      width={width}
      itemHeight={3}
      details={
        <FactDetailsView
          details={factDetails}
          loading={detailsLoading}
          width={detailWidth}
          height={height}
          isFocused={focusPane === "details"}
          focusedSection={detailSection}
          textExpanded={textExpanded}
          textScrollOffset={textScrollOffset}
          entitiesIndex={entitiesIndex}
          linkedIndex={linkedIndex}
          editMode={editMode}
          editText={editText}
          cursorPos={cursorPos}
          setEditText={setEditText}
          setCursorPos={setCursorPos}
          confirmDelete={confirmDelete}
          saving={saving}
        />
      }
    />
  );
}
