import { Box, Text } from "ink";
import type { ObservationDetails } from "../../../api/client.js";
import { colors, truncateText, ExpandableText, ScrollableList, TextInputField } from "../../ui/index.js";
import { useAccentColor } from "../../../hooks/index.js";
import { formatTimeAgo } from "../../../lib/format.js";
import { wrapText } from "../../../lib/utils.js";

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
  // Edit/delete state
  editMode: boolean;
  editText: string;
  cursorPos: number;
  confirmDelete: boolean;
  saving: boolean;
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
  editMode,
  editText,
  cursorPos,
  confirmDelete,
  saving,
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

  const { accentValue } = useAccentColor();
  const { observation, supporting_facts } = details;
  const textColor = isFocused ? colors.text.primary : colors.text.secondary;
  const labelColor = colors.text.muted;
  const valueColor = isFocused ? accentValue : colors.text.secondary;

  const sectionFocused = (section: ObsDetailSection) => isFocused && focusedSection === section;
  const textWidth = width - 2;

  // Calculate visible items for scrollable list
  const factsVisible = SECTION_HEIGHTS.FACTS - 1; // minus header

  if (confirmDelete) {
    return (
      <Box flexDirection="column" width={width} paddingLeft={1}>
        <Text color={colors.status.warning}>
          Delete this observation? This will remove the observation and {details.supporting_facts.length} supporting fact references.
        </Text>
        <Box marginTop={1}>
          <Text color={colors.text.muted}>Press y to confirm, any other key to cancel</Text>
        </Box>
      </Box>
    );
  }

  if (editMode) {
    // Calculate cursor position in wrapped text
    const wrappedLines = wrapText(editText, textWidth);
    let charCount = 0;
    let cursorLine = 0;
    let cursorCol = 0;

    if (wrappedLines.length === 0) {
      cursorLine = 0;
      cursorCol = 0;
    } else {
      for (let i = 0; i < wrappedLines.length; i++) {
        const lineLength = wrappedLines[i].length;
        if (charCount + lineLength >= cursorPos) {
          cursorLine = i;
          cursorCol = cursorPos - charCount;
          break;
        }
        charCount += lineLength;
      }
      // If cursor is at the very end
      if (cursorPos === editText.length && cursorPos > charCount) {
        cursorLine = wrappedLines.length - 1;
        cursorCol = wrappedLines[cursorLine].length;
      }
    }

    return (
      <Box flexDirection="column" width={width} paddingLeft={1}>
        <Text color={colors.text.muted}>EDIT OBSERVATION</Text>
        <Box marginTop={1} flexDirection="column">
          {wrappedLines.length === 0 ? (
            <Text color={colors.text.primary}>
              <Text inverse> </Text>
            </Text>
          ) : (
            wrappedLines.map((line, idx) => (
              <Text key={idx} color={colors.text.primary}>
                {idx === cursorLine ? (
                  <>
                    <Text>{line.slice(0, cursorCol)}</Text>
                    <Text inverse>{line[cursorCol] || " "}</Text>
                    <Text>{line.slice(cursorCol + 1)}</Text>
                  </>
                ) : (
                  line
                )}
              </Text>
            ))
          )}
        </Box>
        {saving ? (
          <Box marginTop={1}>
            <Text color={colors.tool.running}>Saving...</Text>
          </Box>
        ) : (
          <Box marginTop={1}>
            <Text color={colors.text.muted}>Ctrl+S: save  Esc: cancel</Text>
          </Box>
        )}
      </Box>
    );
  }

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
    default: {
      const _exhaustive: never = section;
      return _exhaustive;
    }
  }
}
