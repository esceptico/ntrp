import type { ProfileEntry } from "../../../api/client.js";
import { colors, truncateText, type RenderItemContext } from "../../ui/index.js";
import { formatTimeAgo } from "../../../lib/format.js";
import type { ProfileTabState } from "../../../hooks/useProfileTab.js";
import { ListDetailSection, memoryDetailWidth } from "./ListDetailSection.js";
import { ProfileDetailsView } from "./ProfileDetailsView.js";

interface ProfileSectionProps {
  tab: ProfileTabState;
  height: number;
  width: number;
  saving: boolean;
}

export function ProfileSection({ tab, height, width, saving }: ProfileSectionProps) {
  const listWidth = Math.min(45, Math.max(30, Math.floor(width * 0.4)));
  const detailWidth = memoryDetailWidth(width, listWidth);

  const renderItem = (entry: ProfileEntry, ctx: RenderItemContext) => {
    const textWidth = listWidth - 4;
    const evidence = entry.source_observation_ids.length + entry.source_fact_ids.length;
    const meta = `${entry.kind} · ${Math.round(entry.confidence * 100)}% · ${evidence} sources · ${formatTimeAgo(entry.updated_at)}`;
    return (
      <box flexDirection="column" marginBottom={1}>
        <text><span fg={ctx.colors.text}>{truncateText(entry.summary, textWidth)}</span></text>
        <text><span fg={ctx.isSelected ? colors.text.secondary : colors.text.disabled}>{truncateText(meta, textWidth)}</span></text>
      </box>
    );
  };

  return (
    <ListDetailSection
      items={tab.filteredEntries}
      selectedIndex={tab.selectedIndex}
      renderItem={renderItem}
      getKey={(entry) => entry.id}
      emptyMessage="No curated profile entries"
      searchQuery={tab.searchQuery}
      searchMode={tab.searchMode}
      focusPane={tab.focusPane}
      height={height}
      width={width}
      itemHeight={3}
      totalCount={tab.filteredEntries.length}
      onItemClick={tab.setSelectedIndex}
      details={
        <ProfileDetailsView
          details={tab.entryDetails}
          loading={tab.detailsLoading}
          width={detailWidth}
          height={height}
          isFocused={tab.focusPane === "details"}
          focusedSection={tab.detailSection}
          textExpanded={tab.textExpanded}
          textScrollOffset={tab.textScrollOffset}
          observationsIndex={tab.observationsIndex}
          factsIndex={tab.factsIndex}
          editMode={tab.editMode}
          editText={tab.editText}
          cursorPos={tab.cursorPos}
          setEditText={tab.setEditText}
          setCursorPos={tab.setCursorPos}
          confirmDelete={tab.confirmDelete}
          saving={saving}
        />
      }
    />
  );
}
