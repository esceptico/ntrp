import type { DreamDetails } from "../../../api/client.js";
import { colors, truncateText, ExpandableText, ScrollableList } from "../../ui/index.js";
import { useAccentColor } from "../../../hooks/index.js";
import { formatTimeAgo } from "../../../lib/format.js";

export const DREAM_SECTIONS = {
  TEXT: 0,
  FACTS: 1,
} as const;

export type DreamDetailSection = (typeof DREAM_SECTIONS)[keyof typeof DREAM_SECTIONS];

interface DreamDetailsViewProps {
  details: DreamDetails | null;
  loading: boolean;
  width: number;
  height: number;
  isFocused: boolean;
  focusedSection: DreamDetailSection;
  textExpanded: boolean;
  textScrollOffset: number;
  factsIndex: number;
  confirmDelete: boolean;
}

const TEXT_VISIBLE_LINES = 10;

export function DreamDetailsView({
  details,
  loading,
  width,
  height,
  isFocused,
  focusedSection,
  textExpanded,
  textScrollOffset,
  factsIndex,
  confirmDelete,
}: DreamDetailsViewProps) {
  if (loading) {
    return <text><span fg={colors.text.muted}>Loading...</span></text>;
  }

  if (!details) {
    return (
      <box flexDirection="column" paddingLeft={1}>
        <text><span fg={colors.text.muted}>Select a dream to view details</span></text>
      </box>
    );
  }

  const { accentValue } = useAccentColor();
  const { dream, source_facts } = details;
  const textColor = isFocused ? colors.text.primary : colors.text.secondary;
  const labelColor = colors.text.muted;

  const sectionFocused = (section: DreamDetailSection) => isFocused && focusedSection === section;
  const textWidth = width - 2;

  if (confirmDelete) {
    return (
      <box flexDirection="column" width={width} paddingLeft={1}>
        <text>
          <span fg={colors.status.warning}>
            Delete this dream? This cannot be undone.
          </span>
        </text>
        <box marginTop={1}>
          <text><span fg={colors.text.muted}>Press y to confirm, any other key to cancel</span></text>
        </box>
      </box>
    );
  }

  return (
    <box flexDirection="column" width={width} height={height} paddingLeft={1} overflow="hidden">
      {/* Full insight text */}
      <box>
        <ExpandableText
          text={dream.insight}
          width={textWidth}
          expanded={textExpanded}
          scrollOffset={textScrollOffset}
          visibleLines={TEXT_VISIBLE_LINES}
          isFocused={sectionFocused(DREAM_SECTIONS.TEXT)}
        />
      </box>

      {/* Metadata — single line */}
      <box marginTop={1}>
        <text>
          <span fg={accentValue}>{dream.bridge}</span>
          <span fg={colors.text.disabled}> {"\u2502"} </span>
          <span fg={labelColor}>{formatTimeAgo(dream.created_at)}</span>
        </text>
      </box>

      {/* Source facts */}
      {source_facts.length > 0 && (
        <box flexDirection="column" marginTop={1}>
          <text><span fg={labelColor}>SOURCE FACTS ({source_facts.length})</span></text>
          <ScrollableList
            items={source_facts}
            selectedIndex={factsIndex}
            visibleLines={Math.min(source_facts.length, 8)}
            renderItem={(fact, _idx, selected) => (
              <text>
                <span fg={selected && sectionFocused(DREAM_SECTIONS.FACTS) ? textColor : colors.text.secondary}>
                  {"\u2022"} {truncateText(fact.text, textWidth - 4)}
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

export function getDreamSectionMaxIndex(
  details: DreamDetails | null,
  section: DreamDetailSection
): number {
  if (!details) return 0;
  switch (section) {
    case DREAM_SECTIONS.TEXT:
      return 0;
    case DREAM_SECTIONS.FACTS:
      return Math.max(0, details.source_facts.length - 1);
    default: {
      const _exhaustive: never = section;
      return _exhaustive;
    }
  }
}
