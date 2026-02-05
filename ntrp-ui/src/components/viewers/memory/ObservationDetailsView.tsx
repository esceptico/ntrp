import { Box, Text } from "ink";
import type { ObservationDetails } from "../../../api/client.js";
import { colors, brand, truncateText, ExpandableText, ScrollableList } from "../../ui/index.js";
import { formatTimeAgo } from "../../../lib/format.js";

// Section indices for keyboard navigation
export const OBS_SECTIONS = {
  TEXT: 0,
  FACTS: 1,
} as const;

export type ObsDetailSection = (typeof OBS_SECTIONS)[keyof typeof OBS_SECTIONS];

interface ObservationDetailsViewProps {
  details: ObservationDetails | null;
  loading: boolean;
  width: number;
  isFocused: boolean;
  // Section navigation state
  focusedSection: ObsDetailSection;
  textExpanded: boolean;
  textScrollOffset: number;
  factsIndex: number;
}

// Fixed heights for each section
const SECTION_HEIGHTS = {
  TEXT_COLLAPSED: 1,
  TEXT_EXPANDED: 5,
  METADATA: 2,
  FACTS: 8, // header + 7 items
};

export function ObservationDetailsView({
  details,
  loading,
  width,
  isFocused,
  focusedSection,
  textExpanded,
  textScrollOffset,
  factsIndex,
}: ObservationDetailsViewProps) {
  if (loading) {
    return <Text color={colors.text.muted}>Loading...</Text>;
  }

  if (!details) {
    return (
      <Box flexDirection="column" paddingLeft={1}>
        <Text color={colors.text.muted}>Select an observation to view details</Text>
      </Box>
    );
  }

  const { observation, supporting_facts } = details;
  const textColor = isFocused ? colors.text.primary : colors.text.secondary;
  const labelColor = colors.text.muted;
  const valueColor = isFocused ? brand.primary : colors.text.secondary;

  const sectionFocused = (section: ObsDetailSection) => isFocused && focusedSection === section;
  const textWidth = width - 2;

  // Calculate visible items for scrollable list
  const factsVisible = SECTION_HEIGHTS.FACTS - 1; // minus header

  return (
    <Box flexDirection="column" width={width} paddingLeft={1}>
      {/* Summary section - expandable */}
      <Box>
        <ExpandableText
          text={observation.summary}
          width={textWidth}
          expanded={textExpanded}
          scrollOffset={textScrollOffset}
          visibleLines={SECTION_HEIGHTS.TEXT_EXPANDED}
          isFocused={sectionFocused(OBS_SECTIONS.TEXT)}
          boldFirstLine
        />
      </Box>

      {/* Metadata - fixed, non-interactive */}
      <Box flexDirection="column" height={SECTION_HEIGHTS.METADATA} marginTop={1}>
        <Text>
          <Text color={labelColor}>EVIDENCE </Text>
          <Text color={valueColor}>{observation.evidence_count}</Text>
          <Text color={labelColor}> facts</Text>
          <Text color={colors.text.muted}> │ </Text>
          <Text color={labelColor}>×</Text>
          <Text color={valueColor}>{observation.access_count}</Text>
        </Text>
        <Text>
          <Text color={labelColor}>CREATED </Text>
          <Text color={colors.text.secondary}>{formatTimeAgo(observation.created_at)}</Text>
          <Text color={colors.text.muted}> │ </Text>
          <Text color={labelColor}>UPDATED </Text>
          <Text color={colors.text.secondary}>{formatTimeAgo(observation.updated_at)}</Text>
        </Text>
      </Box>

      {/* Supporting facts section - scrollable list */}
      <Box flexDirection="column" height={SECTION_HEIGHTS.FACTS} marginTop={1}>
        <Text color={labelColor}>
          SUPPORTING FACTS {supporting_facts.length > 0 && `(${supporting_facts.length})`}
        </Text>
        {supporting_facts.length > 0 ? (
          <ScrollableList
            items={supporting_facts}
            selectedIndex={factsIndex}
            visibleLines={factsVisible}
            renderItem={(fact, _idx, selected) => (
              <Text color={selected && sectionFocused(OBS_SECTIONS.FACTS) ? textColor : colors.text.secondary}>
                • {truncateText(fact.text, textWidth - 4)}
              </Text>
            )}
            showScrollArrows={false}
            width={textWidth}
          />
        ) : (
          <Text color={colors.text.muted}>No supporting facts</Text>
        )}
      </Box>
    </Box>
  );
}

// Helper to get max scroll for a section
export function getObsSectionMaxIndex(
  details: ObservationDetails | null,
  section: ObsDetailSection
): number {
  if (!details) return 0;
  switch (section) {
    case OBS_SECTIONS.TEXT:
      return 0;
    case OBS_SECTIONS.FACTS:
      return Math.max(0, details.supporting_facts.length - 1);
  }
}
