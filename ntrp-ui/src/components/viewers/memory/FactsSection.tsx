import React from "react";
import { Text } from "ink";
import type { Fact, FactDetails } from "../../../api/client.js";
import { colors, truncateText, type RenderItemContext } from "../../ui/index.js";
import { useAccentColor } from "../../../hooks/index.js";
import { FactDetailsView, type FactDetailSection } from "./FactDetailsView.js";
import { ListDetailSection } from "./ListDetailSection.js";

interface FactsSectionProps {
  facts: Fact[];
  selectedIndex: number;
  factDetails: FactDetails | null;
  detailsLoading: boolean;
  searchQuery: string;
  focusPane: "list" | "details";
  visibleLines: number;
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

export function FactsSection({
  facts,
  selectedIndex,
  factDetails,
  detailsLoading,
  searchQuery,
  focusPane,
  visibleLines,
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
    const typeChar = fact.fact_type === "world" ? "W" : "E";
    const typeColor = fact.fact_type === "world" ? colors.status.warning : accentValue;
    const textWidth = listWidth - 10;

    return (
      <Text>
        <Text color={ctx.isSelected ? typeColor : colors.text.muted}>[{typeChar}]</Text>
        <Text color={ctx.colors.text}> {truncateText(fact.text, textWidth)}</Text>
      </Text>
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
      focusPane={focusPane}
      visibleLines={visibleLines}
      width={width}
      details={
        <FactDetailsView
          details={factDetails}
          loading={detailsLoading}
          width={detailWidth}
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
