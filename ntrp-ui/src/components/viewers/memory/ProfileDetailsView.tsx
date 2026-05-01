import type { ProfileEntryDetails } from "../../../api/client.js";
import { colors, ExpandableText, ScrollableList, TextEditArea, truncateText } from "../../ui/index.js";
import { useAccentColor } from "../../../hooks/index.js";
import { formatTimeAgo } from "../../../lib/format.js";
import { DeleteConfirmation } from "./DeleteConfirmation.js";

export const PROFILE_SECTIONS = {
  SUMMARY: 0,
  OBSERVATIONS: 1,
  FACTS: 2,
} as const;

export type ProfileDetailSection = (typeof PROFILE_SECTIONS)[keyof typeof PROFILE_SECTIONS];

interface ProfileDetailsViewProps {
  details: ProfileEntryDetails | null;
  loading: boolean;
  width: number;
  height: number;
  isFocused: boolean;
  focusedSection: ProfileDetailSection;
  textExpanded: boolean;
  textScrollOffset: number;
  observationsIndex: number;
  factsIndex: number;
  editMode: boolean;
  editText: string;
  cursorPos: number;
  setEditText: (text: string | ((prev: string) => string)) => void;
  setCursorPos: (pos: number | ((prev: number) => number)) => void;
  confirmDelete: boolean;
  saving: boolean;
}

const SUMMARY_VISIBLE_LINES = 8;

export function ProfileDetailsView({
  details,
  loading,
  width,
  height,
  isFocused,
  focusedSection,
  textExpanded,
  textScrollOffset,
  observationsIndex,
  factsIndex,
  editMode,
  editText,
  cursorPos,
  setEditText,
  setCursorPos,
  confirmDelete,
  saving,
}: ProfileDetailsViewProps) {
  const { accentValue } = useAccentColor();

  if (loading) {
    return <text><span fg={colors.text.muted}>Loading...</span></text>;
  }

  if (!details) {
    return (
      <box flexDirection="column" paddingLeft={1}>
        <text><span fg={colors.text.muted}>No profile entries yet.</span></text>
        <text><span fg={colors.text.disabled}>Profile is curated core memory, not raw facts.</span></text>
      </box>
    );
  }

  const { entry, source_facts, source_observations } = details;
  const textWidth = Math.max(1, width - 2);
  const textColor = isFocused ? colors.text.primary : colors.text.secondary;
  const labelColor = colors.text.muted;
  const sectionFocused = (section: ProfileDetailSection) => isFocused && focusedSection === section;

  if (confirmDelete) {
    return <DeleteConfirmation width={width} height={height} message="Archive this profile entry? Source facts and patterns stay intact." />;
  }

  if (editMode) {
    return (
      <box flexDirection="column" width={width} height={height} paddingLeft={1} overflow="hidden">
        <text><span fg={colors.text.muted}>EDIT PROFILE ENTRY</span></text>
        <box marginTop={1}>
          <TextEditArea
            value={editText}
            cursorPos={cursorPos}
            onValueChange={setEditText}
            onCursorChange={setCursorPos}
            width={textWidth}
            placeholder="Curated profile summary..."
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
      <box marginBottom={1}>
        <text>
          <span fg={accentValue}>profile entry</span>
          <span fg={colors.text.disabled}> {"\u2502"} curated core memory</span>
        </text>
      </box>

      <ExpandableText
        text={entry.summary}
        width={textWidth}
        expanded={textExpanded}
        scrollOffset={textScrollOffset}
        visibleLines={SUMMARY_VISIBLE_LINES}
        isFocused={sectionFocused(PROFILE_SECTIONS.SUMMARY)}
      />

      <box marginTop={1}>
        <text>
          <span fg={accentValue}>{entry.kind}</span>
          <span fg={colors.text.disabled}> {"\u2502"} </span>
          <span fg={labelColor}>confidence {Math.round(entry.confidence * 100)}%</span>
          <span fg={colors.text.disabled}> {"\u2502"} </span>
          <span fg={labelColor}>updated {formatTimeAgo(entry.updated_at)}</span>
          <span fg={colors.text.disabled}> {"\u2502"} </span>
          <span fg={labelColor}>{entry.created_by}</span>
        </text>
      </box>

      <box flexDirection="column" marginTop={1}>
        <text><span fg={labelColor}>PROVENANCE</span></text>
        <text>
          <span fg={colors.text.secondary}>{source_observations.length}</span>
          <span fg={colors.text.disabled}> patterns, </span>
          <span fg={colors.text.secondary}>{source_facts.length}</span>
          <span fg={colors.text.disabled}> facts loaded as direct evidence</span>
        </text>
      </box>

      {source_observations.length > 0 && (
        <box flexDirection="column" marginTop={1}>
          <text><span fg={labelColor}>SOURCE PATTERNS ({source_observations.length})</span></text>
          <ScrollableList
            items={source_observations}
            selectedIndex={observationsIndex}
            visibleLines={Math.min(source_observations.length, 5)}
            renderItem={(observation, _idx, selected) => (
              <text>
                <span fg={selected && sectionFocused(PROFILE_SECTIONS.OBSERVATIONS) ? textColor : colors.text.secondary}>
                  {"\u2022"} {truncateText(observation.summary, Math.max(1, textWidth - 2))}
                </span>
              </text>
            )}
            width={textWidth}
          />
        </box>
      )}

      {source_facts.length > 0 && (
        <box flexDirection="column" marginTop={1}>
          <text><span fg={labelColor}>SOURCE FACTS ({source_facts.length})</span></text>
          <ScrollableList
            items={source_facts}
            selectedIndex={factsIndex}
            visibleLines={Math.min(source_facts.length, 6)}
            renderItem={(fact, _idx, selected) => (
              <text>
                <span fg={selected && sectionFocused(PROFILE_SECTIONS.FACTS) ? textColor : colors.text.secondary}>
                  {"\u2022"} {truncateText(fact.text, Math.max(1, textWidth - 2))}
                </span>
              </text>
            )}
            width={textWidth}
          />
        </box>
      )}
    </box>
  );
}

export function getProfileSectionMaxIndex(
  details: ProfileEntryDetails | null,
  section: ProfileDetailSection,
): number {
  if (!details) return 0;
  switch (section) {
    case PROFILE_SECTIONS.SUMMARY:
      return 0;
    case PROFILE_SECTIONS.OBSERVATIONS:
      return Math.max(0, details.source_observations.length - 1);
    case PROFILE_SECTIONS.FACTS:
      return Math.max(0, details.source_facts.length - 1);
    default: {
      const _exhaustive: never = section;
      return _exhaustive;
    }
  }
}
