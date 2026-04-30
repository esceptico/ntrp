import type { ObservationDetails } from "../../../api/client.js";
import { colors, truncateText, ExpandableText, ScrollableList, TextEditArea } from "../../ui/index.js";
import { useAccentColor } from "../../../hooks/index.js";
import { formatTimeAgo } from "../../../lib/format.js";
import { DeleteConfirmation } from "./DeleteConfirmation.js";

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
  height: number;
  isFocused: boolean;
  focusedSection: ObsDetailSection;
  textExpanded: boolean;
  textScrollOffset: number;
  factsIndex: number;
  editMode: boolean;
  editText: string;
  cursorPos: number;
  setEditText: (text: string | ((prev: string) => string)) => void;
  setCursorPos: (pos: number | ((prev: number) => number)) => void;
  confirmDelete: boolean;
  saving: boolean;
}

const TEXT_VISIBLE_LINES = 10;

export function ObservationDetailsView({
  details,
  loading,
  width,
  height,
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
  const { accentValue } = useAccentColor();

  if (loading) {
    return <text><span fg={colors.text.muted}>Loading...</span></text>;
  }

  if (!details) {
    return (
      <box flexDirection="column" paddingLeft={1}>
        <text><span fg={colors.text.muted}>Select a pattern to view details</span></text>
      </box>
    );
  }
  const { observation, supporting_facts } = details;
  const textColor = isFocused ? colors.text.primary : colors.text.secondary;
  const labelColor = colors.text.muted;

  const sectionFocused = (section: ObsDetailSection) => isFocused && focusedSection === section;
  const textWidth = width - 2;

  if (confirmDelete) {
    return <DeleteConfirmation width={width} height={height} message={`Delete this pattern? This will remove the pattern and ${details.supporting_facts.length} supporting fact references.`} />;
  }

  if (editMode) {
    return (
      <box flexDirection="column" width={width} height={height} paddingLeft={1} overflow="hidden">
        <text><span fg={colors.text.muted}>EDIT PATTERN</span></text>
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
    <box flexDirection="column" width={width} height={height} paddingLeft={1} overflow="hidden">
      {/* Full text */}
      <box>
        <ExpandableText
          text={observation.summary}
          width={textWidth}
          expanded={textExpanded}
          scrollOffset={textScrollOffset}
          visibleLines={TEXT_VISIBLE_LINES}
          isFocused={sectionFocused(OBS_SECTIONS.TEXT)}
        />
      </box>

      {/* Metadata — single line */}
      <box marginTop={1}>
        <text>
          <span fg={accentValue}>pattern</span>
          <span fg={colors.text.disabled}> {"\u2502"} </span>
          <span fg={labelColor}>{observation.evidence_count} facts</span>
          <span fg={colors.text.disabled}> {"\u2502"} </span>
          <span fg={labelColor}>{"\u00D7"}{observation.access_count}</span>
          <span fg={colors.text.disabled}> {"\u2502"} </span>
          <span fg={labelColor}>created {formatTimeAgo(observation.created_at)}</span>
          <span fg={colors.text.disabled}> {"\u2502"} </span>
          <span fg={labelColor}>{observation.access_count ? `used ${formatTimeAgo(observation.last_accessed_at)}` : "never used"}</span>
          {observation.archived_at && (
            <>
              <span fg={colors.text.disabled}> {"\u2502"} </span>
              <span fg={colors.status.error}>archived</span>
            </>
          )}
        </text>
      </box>

      {/* Supporting facts — only if non-empty */}
      {supporting_facts.length > 0 && (
        <box flexDirection="column" marginTop={1}>
          <text><span fg={labelColor}>SUPPORTING FACTS ({supporting_facts.length})</span></text>
          <ScrollableList
            items={supporting_facts}
            selectedIndex={factsIndex}
            visibleLines={Math.min(supporting_facts.length, 8)}
            renderItem={(fact, _idx, selected) => {
              const status = fact.archived_at
                ? "archived"
                : fact.superseded_by_fact_id
                  ? `superseded:${fact.superseded_by_fact_id}`
                  : fact.expires_at && new Date(fact.expires_at) <= new Date()
                    ? "expired"
                    : "active";
              const meta = `${fact.kind} · ${fact.source_type} · ${status}`;
              const bodyWidth = Math.max(10, textWidth - meta.length - 7);
              return (
                <text>
                  <span fg={selected && sectionFocused(OBS_SECTIONS.FACTS) ? textColor : colors.text.secondary}>
                    {"\u2022"} {truncateText(fact.text, bodyWidth)}
                  </span>
                  <span fg={colors.text.disabled}>  {meta}</span>
                </text>
              );
            }}
            width={textWidth}
          />
        </box>
      )}
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
