import type { FactDetails } from "../../../api/client.js";
import { colors, truncateText, ExpandableText, ScrollableList, TextEditArea } from "../../ui/index.js";
import { useAccentColor } from "../../../hooks/index.js";
import { formatTimeAgo } from "../../../lib/format.js";

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
  height: number;
  isFocused: boolean;
  focusedSection: FactDetailSection;
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

const TEXT_VISIBLE_LINES = 10;

export function FactDetailsView({
  details,
  loading,
  width,
  height,
  isFocused,
  focusedSection,
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
}: FactDetailsViewProps) {
  if (loading) {
    return <text><span fg={colors.text.muted}>Loading...</span></text>;
  }

  if (!details) {
    return (
      <box flexDirection="column" paddingLeft={1}>
        <text><span fg={colors.text.muted}>Select a fact to view details</span></text>
      </box>
    );
  }

  const { accentValue } = useAccentColor();
  const { fact, entities, linked_facts } = details;
  const textColor = isFocused ? colors.text.primary : colors.text.secondary;
  const labelColor = colors.text.muted;

  const typeLabel = fact.fact_type === "world" ? "world" : "experience";
  const typeColor = fact.fact_type === "world" ? colors.status.warning : accentValue;

  const sectionFocused = (section: FactDetailSection) => isFocused && focusedSection === section;
  const textWidth = width - 2;

  if (confirmDelete) {
    return (
      <box flexDirection="column" width={width} paddingLeft={1}>
        <text>
          <span fg={colors.status.warning}>
            Delete this fact? This will remove {details.entities.length} entities, {details.linked_facts.length} links.
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
        <text><span fg={colors.text.muted}>EDIT FACT</span></text>
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
          text={fact.text}
          width={textWidth}
          expanded={textExpanded}
          scrollOffset={textScrollOffset}
          visibleLines={TEXT_VISIBLE_LINES}
          isFocused={sectionFocused(FACT_SECTIONS.TEXT)}
        />
      </box>

      {/* Metadata — single line */}
      <box marginTop={1}>
        <text>
          <span fg={typeColor}>{typeLabel}</span>
          <span fg={colors.text.disabled}> {"\u2502"} </span>
          <span fg={labelColor}>{fact.source_type}</span>
          <span fg={colors.text.disabled}> {"\u2502"} </span>
          <span fg={labelColor}>{"\u00D7"}{fact.access_count}</span>
          <span fg={colors.text.disabled}> {"\u2502"} </span>
          <span fg={labelColor}>{formatTimeAgo(fact.created_at)}</span>
        </text>
      </box>

      {/* Entities — only if non-empty */}
      {entities.length > 0 && (
        <box flexDirection="column" marginTop={1}>
          <text><span fg={labelColor}>ENTITIES ({entities.length})</span></text>
          <ScrollableList
            items={entities}
            selectedIndex={entitiesIndex}
            visibleLines={Math.min(entities.length, 6)}
            renderItem={(entity, _idx, selected) => (
              <text>
                <span fg={selected && sectionFocused(FACT_SECTIONS.ENTITIES) ? textColor : colors.text.secondary}>
                  {"\u2022"} {entity.name}{" "}
                </span>
                <span fg={colors.text.muted}>({entity.type})</span>
              </text>
            )}
            width={textWidth}
          />
        </box>
      )}

      {/* Linked facts — only if non-empty */}
      {linked_facts.length > 0 && (
        <box flexDirection="column" marginTop={1}>
          <text><span fg={labelColor}>LINKED ({linked_facts.length})</span></text>
          <ScrollableList
            items={linked_facts}
            selectedIndex={linkedIndex}
            visibleLines={Math.min(linked_facts.length, 6)}
            renderItem={(lf, _idx, selected) => {
              const linkColor =
                lf.link_type === "semantic"
                  ? colors.text.muted
                  : lf.link_type === "entity"
                    ? accentValue
                    : colors.status.warning;
              return (
                <text>
                  <span fg={linkColor}>[{lf.link_type.charAt(0)}]</span>
                  <span fg={selected && sectionFocused(FACT_SECTIONS.LINKED) ? textColor : colors.text.secondary}>
                    {" "}{truncateText(lf.text, textWidth - 4)}
                  </span>
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
    default: {
      const _exhaustive: never = section;
      return _exhaustive;
    }
  }
}
