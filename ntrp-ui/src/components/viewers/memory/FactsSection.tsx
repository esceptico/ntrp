import React from "react";
import { Box, Text } from "ink";
import type { Fact, FactDetails } from "../../../api/client.js";
import {
  SplitView,
  BaseSelectionList,
  colors,
  brand,
  truncateText,
  type RenderItemContext,
} from "../../ui/index.js";
import { FactDetailsView, type FactDetailSection } from "./FactDetailsView.js";

interface FactsSectionProps {
  facts: Fact[];
  selectedIndex: number;
  factDetails: FactDetails | null;
  detailsLoading: boolean;
  searchQuery: string;
  focusPane: "list" | "details";
  visibleLines: number;
  width: number;
  // New detail section state
  detailSection: FactDetailSection;
  textExpanded: boolean;
  textScrollOffset: number;
  entitiesIndex: number;
  linkedIndex: number;
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
}: FactsSectionProps) {
  const listWidth = Math.min(45, Math.max(30, Math.floor(width * 0.4)));
  const detailWidth = Math.max(0, width - listWidth - 1);

  const renderItem = (fact: Fact, ctx: RenderItemContext) => {
    const typeChar = fact.fact_type === "world" ? "W" : "E";
    const typeColor = fact.fact_type === "world" ? colors.status.warning : brand.primary;
    const textWidth = listWidth - 10;

    return (
      <Text>
        <Text color={ctx.isSelected ? typeColor : colors.text.muted}>[{typeChar}]</Text>
        <Text color={ctx.colors.text}> {truncateText(fact.text, textWidth)}</Text>
      </Text>
    );
  };

  const sidebar = (
    <Box flexDirection="column">
      {searchQuery && (
        <Box marginBottom={1}>
          <Text color={colors.text.muted}>/{searchQuery}</Text>
        </Box>
      )}
      <BaseSelectionList
        items={facts}
        selectedIndex={selectedIndex}
        renderItem={renderItem}
        visibleLines={visibleLines}
        getKey={(f) => f.id}
        emptyMessage="No facts stored yet"
        showScrollArrows
        width={listWidth}
      />
      {facts.length > 0 && (
        <Box marginTop={1}>
          <Text color={colors.text.muted}>
            {selectedIndex + 1}/{facts.length}
          </Text>
        </Box>
      )}
    </Box>
  );

  const main = (
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
    />
  );

  return (
    <Box marginY={1} height={visibleLines + 3}>
      <SplitView sidebarWidth={listWidth} sidebar={sidebar} main={main} />
    </Box>
  );
}
