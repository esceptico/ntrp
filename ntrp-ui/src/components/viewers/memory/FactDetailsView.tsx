import { Box, Text } from "ink";
import type { FactDetails } from "../../../api/client.js";
import { colors, brand, truncateText, ExpandableText, ScrollableList } from "../../ui/index.js";

// Section indices for keyboard navigation
export const FACT_SECTIONS = {
  TEXT: 0,
  ENTITIES: 1,
  LINKED: 2,
} as const;

export type FactDetailSection = (typeof FACT_SECTIONS)[keyof typeof FACT_SECTIONS];

interface FactDetailsViewProps {
  details: FactDetails | null;
  loading: boolean;
  width: number;
  isFocused: boolean;
  // Section navigation state
  focusedSection: FactDetailSection;
  textExpanded: boolean;
  textScrollOffset: number;
  entitiesIndex: number;
  linkedIndex: number;
}

// Fixed heights for each section
const SECTION_HEIGHTS = {
  TEXT_COLLAPSED: 1,
  TEXT_EXPANDED: 5,
  METADATA: 2,
  ENTITIES: 4, // header + 3 items
  LINKED: 5, // header + 4 items
};

function formatTimeAgo(isoDate: string): string {
  const date = new Date(isoDate);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));

  if (diffHours < 1) return "just now";
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays === 1) return "yesterday";
  if (diffDays < 7) return `${diffDays}d ago`;
  const diffWeeks = Math.floor(diffDays / 7);
  if (diffWeeks === 1) return "1 week ago";
  if (diffWeeks < 4) return `${diffWeeks} weeks ago`;
  return date.toLocaleDateString();
}

export function FactDetailsView({
  details,
  loading,
  width,
  isFocused,
  focusedSection,
  textExpanded,
  textScrollOffset,
  entitiesIndex,
  linkedIndex,
}: FactDetailsViewProps) {
  if (loading) {
    return <Text color={colors.text.muted}>Loading...</Text>;
  }

  if (!details) {
    return (
      <Box flexDirection="column" paddingLeft={1}>
        <Text color={colors.text.muted}>Select a fact to view details</Text>
      </Box>
    );
  }

  const { fact, entities, linked_facts } = details;
  const textColor = isFocused ? colors.text.primary : colors.text.secondary;
  const labelColor = colors.text.muted;
  const valueColor = isFocused ? brand.primary : colors.text.secondary;

  const typeLabel = fact.fact_type === "world" ? "WORLD" : "EXPERIENCE";
  const typeColor = fact.fact_type === "world" ? colors.status.warning : brand.primary;

  const sectionFocused = (section: FactDetailSection) => isFocused && focusedSection === section;
  const textWidth = width - 2;

  // Calculate visible items for scrollable lists
  const entitiesVisible = SECTION_HEIGHTS.ENTITIES - 1; // minus header
  const linkedVisible = SECTION_HEIGHTS.LINKED - 1; // minus header

  return (
    <Box flexDirection="column" width={width} paddingLeft={1}>
      {/* Text section - expandable */}
      <Box>
        <ExpandableText
          text={fact.text}
          width={textWidth}
          expanded={textExpanded}
          scrollOffset={textScrollOffset}
          visibleLines={SECTION_HEIGHTS.TEXT_EXPANDED}
          isFocused={sectionFocused(FACT_SECTIONS.TEXT)}
          boldFirstLine
        />
      </Box>

      {/* Metadata - fixed, non-interactive */}
      <Box flexDirection="column" height={SECTION_HEIGHTS.METADATA} marginTop={1}>
        <Text>
          <Text color={labelColor}>TYPE </Text>
          <Text color={typeColor}>{typeLabel}</Text>
          <Text color={colors.text.muted}> │ </Text>
          <Text color={labelColor}>SRC </Text>
          <Text color={valueColor}>{fact.source_type}</Text>
          <Text color={colors.text.muted}> │ </Text>
          <Text color={labelColor}>×</Text>
          <Text color={valueColor}>{fact.access_count}</Text>
        </Text>
        <Text>
          <Text color={labelColor}>CREATED </Text>
          <Text color={colors.text.secondary}>{formatTimeAgo(fact.created_at)}</Text>
        </Text>
      </Box>

      {/* Entities section - scrollable list */}
      <Box flexDirection="column" height={SECTION_HEIGHTS.ENTITIES} marginTop={1}>
        <Text color={labelColor}>
          ENTITIES {entities.length > 0 && `(${entities.length})`}
        </Text>
        {entities.length > 0 ? (
          <ScrollableList
            items={entities}
            selectedIndex={entitiesIndex}
            visibleLines={entitiesVisible}
            renderItem={(entity, _idx, selected) => (
              <Text color={selected && sectionFocused(FACT_SECTIONS.ENTITIES) ? textColor : colors.text.secondary}>
                • {entity.name}{" "}
                <Text color={colors.text.muted}>({entity.type})</Text>
              </Text>
            )}
            showScrollArrows={false}
            width={textWidth}
          />
        ) : (
          <Text color={colors.text.muted}>No entities</Text>
        )}
      </Box>

      {/* Linked facts section - scrollable list */}
      <Box flexDirection="column" height={SECTION_HEIGHTS.LINKED} marginTop={1}>
        <Text color={labelColor}>
          LINKED {linked_facts.length > 0 && `(${linked_facts.length})`}
        </Text>
        {linked_facts.length > 0 ? (
          <ScrollableList
            items={linked_facts}
            selectedIndex={linkedIndex}
            visibleLines={linkedVisible}
            renderItem={(lf, _idx, selected) => {
              const linkColor =
                lf.link_type === "semantic"
                  ? colors.text.muted
                  : lf.link_type === "entity"
                    ? brand.primary
                    : colors.status.warning;
              return (
                <Text>
                  <Text color={linkColor}>[{lf.link_type.charAt(0)}]</Text>
                  <Text color={selected && sectionFocused(FACT_SECTIONS.LINKED) ? textColor : colors.text.secondary}>
                    {" "}{truncateText(lf.text, textWidth - 4)}
                  </Text>
                </Text>
              );
            }}
            showScrollArrows={false}
            width={textWidth}
          />
        ) : (
          <Text color={colors.text.muted}>No linked facts</Text>
        )}
      </Box>
    </Box>
  );
}

// Helper to get max scroll for a section
export function getFactSectionMaxIndex(
  details: FactDetails | null,
  section: FactDetailSection
): number {
  if (!details) return 0;
  switch (section) {
    case FACT_SECTIONS.TEXT:
      return 0;
    case FACT_SECTIONS.ENTITIES:
      return Math.max(0, details.entities.length - 1);
    case FACT_SECTIONS.LINKED:
      return Math.max(0, details.linked_facts.length - 1);
  }
}
