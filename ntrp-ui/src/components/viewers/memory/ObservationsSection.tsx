import React from "react";
import { Box, Text } from "ink";
import type { Observation, ObservationDetails } from "../../../api/client.js";
import {
  SplitView,
  BaseSelectionList,
  colors,
  brand,
  truncateText,
  type RenderItemContext,
} from "../../ui/index.js";
import { ObservationDetailsView, type ObsDetailSection } from "./ObservationDetailsView.js";

interface ObservationsSectionProps {
  observations: Observation[];
  selectedIndex: number;
  obsDetails: ObservationDetails | null;
  detailsLoading: boolean;
  searchQuery: string;
  focusPane: "list" | "details";
  visibleLines: number;
  width: number;
  // New detail section state
  detailSection: ObsDetailSection;
  textExpanded: boolean;
  textScrollOffset: number;
  factsIndex: number;
}

export function ObservationsSection({
  observations,
  selectedIndex,
  obsDetails,
  detailsLoading,
  searchQuery,
  focusPane,
  visibleLines,
  width,
  detailSection,
  textExpanded,
  textScrollOffset,
  factsIndex,
}: ObservationsSectionProps) {
  const listWidth = Math.min(45, Math.max(30, Math.floor(width * 0.4)));
  const detailWidth = Math.max(0, width - listWidth - 1);

  const renderItem = (obs: Observation, ctx: RenderItemContext) => {
    const textWidth = listWidth - 10;
    const countColor = ctx.isSelected ? brand.primary : colors.text.muted;

    return (
      <Text>
        <Text color={countColor}>[{obs.evidence_count}]</Text>
        <Text color={ctx.colors.text}> {truncateText(obs.summary, textWidth)}</Text>
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
        items={observations}
        selectedIndex={selectedIndex}
        renderItem={renderItem}
        visibleLines={visibleLines}
        getKey={(o) => o.id}
        emptyMessage="No observations synthesized yet"
        showScrollArrows
        width={listWidth}
      />
      {observations.length > 0 && (
        <Box marginTop={1}>
          <Text color={colors.text.muted}>
            {selectedIndex + 1}/{observations.length}
          </Text>
        </Box>
      )}
    </Box>
  );

  const main = (
    <ObservationDetailsView
      details={obsDetails}
      loading={detailsLoading}
      width={detailWidth}
      isFocused={focusPane === "details"}
      focusedSection={detailSection}
      textExpanded={textExpanded}
      textScrollOffset={textScrollOffset}
      factsIndex={factsIndex}
    />
  );

  return (
    <Box marginY={1} height={visibleLines + 3}>
      <SplitView sidebarWidth={listWidth} sidebar={sidebar} main={main} />
    </Box>
  );
}
