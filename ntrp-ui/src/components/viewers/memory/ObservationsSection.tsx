import type { Observation, ObservationDetails } from "../../../api/client.js";
import { colors, truncateText, type RenderItemContext } from "../../ui/index.js";
import { useAccentColor } from "../../../hooks/index.js";
import { formatTimeAgo } from "../../../lib/format.js";
import { ObservationDetailsView, type ObsDetailSection } from "./ObservationDetailsView.js";
import { ListDetailSection } from "./ListDetailSection.js";

interface ObservationsSectionProps {
  observations: Observation[];
  selectedIndex: number;
  obsDetails: ObservationDetails | null;
  detailsLoading: boolean;
  searchQuery: string;
  searchMode: boolean;
  focusPane: "list" | "details";
  height: number;
  width: number;
  detailSection: ObsDetailSection;
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

function shortTime(iso: string): string {
  const full = formatTimeAgo(iso);
  return full.replace(" ago", "");
}

export function ObservationsSection({
  observations,
  selectedIndex,
  obsDetails,
  detailsLoading,
  searchQuery,
  searchMode,
  focusPane,
  height,
  width,
  detailSection,
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
}: ObservationsSectionProps) {
  const { accentValue } = useAccentColor();
  const listWidth = Math.min(45, Math.max(30, Math.floor(width * 0.4)));
  const detailWidth = Math.max(0, width - listWidth - 1);

  const renderItem = (obs: Observation, ctx: RenderItemContext) => {
    const textWidth = listWidth - 4;
    const tagColor = ctx.isSelected ? colors.text.secondary : colors.text.disabled;

    return (
      <box flexDirection="column" marginBottom={1}>
        <text>
          <span fg={ctx.colors.text}>{truncateText(obs.summary, textWidth)}</span>
        </text>
        <text>
          <span fg={ctx.isSelected ? accentValue : tagColor}>[{obs.evidence_count}]</span>
          <span fg={tagColor}> [{shortTime(obs.created_at)}]</span>
        </text>
      </box>
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
      searchMode={searchMode}
      focusPane={focusPane}
      height={height}
      width={width}
      itemHeight={3}
      details={
        <ObservationDetailsView
          details={obsDetails}
          loading={detailsLoading}
          width={detailWidth}
          height={height}
          isFocused={focusPane === "details"}
          focusedSection={detailSection}
          textExpanded={textExpanded}
          textScrollOffset={textScrollOffset}
          factsIndex={factsIndex}
          editMode={editMode}
          editText={editText}
          cursorPos={cursorPos}
          setEditText={setEditText}
          setCursorPos={setCursorPos}
          confirmDelete={confirmDelete}
          saving={saving}
        />
      }
    />
  );
}
