import type { Fact } from "../../../api/client.js";
import { colors, truncateText, type RenderItemContext } from "../../ui/index.js";
import { shortTime } from "../../../lib/format.js";
import type { FactsTabState } from "../../../hooks/useFactsTab.js";
import { FactDetailsView } from "./FactDetailsView.js";
import { ListDetailSection } from "./ListDetailSection.js";

interface FactsSectionProps {
  tab: FactsTabState;
  height: number;
  width: number;
  saving: boolean;
  emptyMessage?: string;
}

export function FactsSection({ tab, height, width, saving, emptyMessage = "No facts match filters" }: FactsSectionProps) {
  const listWidth = Math.min(45, Math.max(30, Math.floor(width * 0.4)));
  const detailWidth = Math.max(0, width - listWidth - 1);

  const renderItem = (fact: Fact, ctx: RenderItemContext) => {
    const textWidth = listWidth - 4;
    const tagColor = ctx.isSelected ? colors.text.secondary : colors.text.disabled;
    const status =
      fact.archived_at ? "arch" :
      fact.superseded_by_fact_id ? "sup" :
      fact.expires_at ? "tmp" :
      fact.pinned_at ? "pin" :
      "act";

    return (
      <box flexDirection="column" marginBottom={1}>
        <text>
          <span fg={ctx.colors.text}>{truncateText(fact.text, textWidth)}</span>
        </text>
        <text>
          <span fg={tagColor}>
            {fact.kind} · {fact.source_type} · importance {fact.salience}/2 · {status} · {shortTime(fact.created_at)}
          </span>
        </text>
      </box>
    );
  };

  return (
    <ListDetailSection
      items={tab.filteredFacts}
      selectedIndex={tab.selectedIndex}
      renderItem={renderItem}
      getKey={(f) => f.id}
      emptyMessage={emptyMessage}
      searchQuery={tab.searchQuery}
      searchMode={tab.searchMode}
      focusPane={tab.focusPane}
      height={height}
      width={width}
      itemHeight={3}
      totalCount={tab.factTotal}
      onItemClick={tab.setSelectedIndex}
      details={
        <FactDetailsView
          details={tab.factDetails}
          loading={tab.detailsLoading}
          width={detailWidth}
          height={height}
          isFocused={tab.focusPane === "details"}
          focusedSection={tab.detailSection}
          textExpanded={tab.textExpanded}
          textScrollOffset={tab.textScrollOffset}
          entitiesIndex={tab.entitiesIndex}
          linkedIndex={tab.linkedIndex}
          editMode={tab.editMode}
          editText={tab.editText}
          cursorPos={tab.cursorPos}
          setEditText={tab.setEditText}
          setCursorPos={tab.setCursorPos}
          confirmDelete={tab.confirmDelete}
          saving={saving}
          metadataSuggestion={tab.metadataSuggestion}
          suggestionLoading={tab.suggestionLoading}
          suggestionError={tab.suggestionError}
        />
      }
    />
  );
}
