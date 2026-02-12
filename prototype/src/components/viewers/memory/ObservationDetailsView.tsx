import type { ObservationDetails } from "../../../api/client.js";
import { colors, truncateText, ExpandableText, ScrollableList, TextEditArea } from "../../ui/index.js";
import { useAccentColor } from "../../../hooks/index.js";
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
  // Edit/delete state
  editMode: boolean;
  editText: string;
  cursorPos: number;
  setEditText: (text: string | ((prev: string) => string)) => void;
  setCursorPos: (pos: number | ((prev: number) => number)) => void;
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
  setEditText,
  setCursorPos,
  confirmDelete,
  saving,
}: ObservationDetailsViewProps) {
  if (loading) {
    return <text><span fg={colors.text.muted}>Loading...</span></text>;
  }

  if (!details) {
    return (
      <box flexDirection="column" paddingLeft={1}>
        <text><span fg={colors.text.muted}>Select an observation to view details</span></text>
      </box>
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
      <box flexDirection="column" width={width} paddingLeft={1}>
        <text>
          <span fg={colors.status.warning}>
            Delete this observation? This will remove the observation and {details.supporting_facts.length} supporting fact references.
          </span>
        </text>
        <box marginTop={1}>
          <text><span fg={colors.text.muted}>Press y to confirm, any other key to cancel</span></text>
        </box>
      </box>
    );
  }

  if (editMode) {
    return (
      <box flexDirection="column" width={width} paddingLeft={1}>
        <text><span fg={colors.text.muted}>EDIT OBSERVATION</span></text>
        <box marginTop={1}>
          <TextEditArea
            value={editText}
            cursorPos={cursorPos}
            onValueChange={setEditText}
            onCursorChange={setCursorPos}
            placeholder="Type to edit..."
          />
        </box>
        {saving && (
          <box marginTop={1}>
            <text><span fg={colors.tool.running}>Saving...</span></text>
          </box>
        )}
      </box>
    );
  }

  return (
    <box flexDirection="column" width={width} paddingLeft={1}>
      {/* Summary section - expandable */}
      <box>
        <ExpandableText
          text={observation.summary}
          width={textWidth}
          expanded={textExpanded}
          scrollOffset={textScrollOffset}
          visibleLines={SECTION_HEIGHTS.TEXT_EXPANDED}
          isFocused={sectionFocused(OBS_SECTIONS.TEXT)}
          boldFirstLine
        />
      </box>

      {/* Metadata - fixed, non-interactive */}
      <box flexDirection="column" height={SECTION_HEIGHTS.METADATA} marginTop={1}>
        <text>
          <span fg={labelColor}>EVIDENCE </span>
          <span fg={valueColor}>{observation.evidence_count}</span>
          <span fg={labelColor}> facts</span>
          <span fg={colors.text.muted}> {"\u2502"} </span>
          <span fg={labelColor}>{"\u00D7"}</span>
          <span fg={valueColor}>{observation.access_count}</span>
        </text>
        <text>
          <span fg={labelColor}>CREATED </span>
          <span fg={colors.text.secondary}>{formatTimeAgo(observation.created_at)}</span>
          <span fg={colors.text.muted}> {"\u2502"} </span>
          <span fg={labelColor}>UPDATED </span>
          <span fg={colors.text.secondary}>{formatTimeAgo(observation.updated_at)}</span>
        </text>
      </box>

      {/* Supporting facts section - scrollable list */}
      <box flexDirection="column" height={SECTION_HEIGHTS.FACTS} marginTop={1}>
        <text>
          <span fg={labelColor}>
            SUPPORTING FACTS {supporting_facts.length > 0 && `(${supporting_facts.length})`}
          </span>
        </text>
        {supporting_facts.length > 0 ? (
          <ScrollableList
            items={supporting_facts}
            selectedIndex={factsIndex}
            visibleLines={factsVisible}
            renderItem={(fact, _idx, selected) => (
              <text>
                <span fg={selected && sectionFocused(OBS_SECTIONS.FACTS) ? textColor : colors.text.secondary}>
                  {"\u2022"} {truncateText(fact.text, textWidth - 4)}
                </span>
              </text>
            )}
            width={textWidth}
          />
        ) : (
          <text><span fg={colors.text.muted}>No supporting facts</span></text>
        )}
      </box>
    </box>
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
