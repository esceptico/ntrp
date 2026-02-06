import React from "react";
import { Text } from "ink";
import type { Observation, ObservationDetails } from "../../../api/client.js";
import { colors, truncateText, type RenderItemContext } from "../../ui/index.js";
import { useAccentColor } from "../../../hooks/index.js";
import { ObservationDetailsView, type ObsDetailSection } from "./ObservationDetailsView.js";
import { ListDetailSection } from "./ListDetailSection.js";

interface ObservationsSectionProps {
  observations: Observation[];
  selectedIndex: number;
  obsDetails: ObservationDetails | null;
  detailsLoading: boolean;
  searchQuery: string;
  focusPane: "list" | "details";
  visibleLines: number;
  width: number;
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
  const { accentValue } = useAccentColor();
  const listWidth = Math.min(45, Math.max(30, Math.floor(width * 0.4)));
  const detailWidth = Math.max(0, width - listWidth - 1);

  const renderItem = (obs: Observation, ctx: RenderItemContext) => {
    const textWidth = listWidth - 10;
    const countColor = ctx.isSelected ? accentValue : colors.text.muted;

    return (
      <Text>
        <Text color={countColor}>[{obs.evidence_count}]</Text>
        <Text color={ctx.colors.text}> {truncateText(obs.summary, textWidth)}</Text>
      </Text>
    );
  };

  return (
    <ListDetailSection
      items={observations}
      selectedIndex={selectedIndex}
      renderItem={renderItem}
      getKey={(o) => o.id}
      emptyMessage="No observations synthesized yet"
      searchQuery={searchQuery}
      focusPane={focusPane}
      visibleLines={visibleLines}
      width={width}
      details={
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
      }
    />
  );
}
