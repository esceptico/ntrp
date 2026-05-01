import type { Fact } from "../../../api/client.js";
import { colors, truncateText, type RenderItemContext } from "../../ui/index.js";
import { formatCountdown, shortTime } from "../../../lib/format.js";
import type { FactsTabState } from "../../../hooks/useFactsTab.js";
import { FactDetailsView } from "./FactDetailsView.js";
import { ListDetailSection, memoryDetailWidth } from "./ListDetailSection.js";

export interface FactReviewMarker {
  reasons: string[];
  recommendation: string;
}

interface FactsSectionProps {
  tab: FactsTabState;
  height: number;
  width: number;
  saving: boolean;
  emptyMessage?: string;
  reviewMarkers?: Map<number, FactReviewMarker>;
}

const REVIEW_REASON_LABELS: Record<string, string> = {
  pinned_non_profile: "pinned non-profile",
  important_non_profile: "important non-profile",
  reused_non_profile: "reused non-profile",
  profile_overlong: "overlong",
  profile_low_confidence: "low confidence",
};

function reviewLabel(marker: FactReviewMarker): string {
  const reasons = marker.reasons.map((reason) => REVIEW_REASON_LABELS[reason] ?? reason).join(", ");
  return `review: ${reasons}`;
}

export function FactsSection({
  tab,
  height,
  width,
  saving,
  emptyMessage = "No facts match filters",
  reviewMarkers,
}: FactsSectionProps) {
  const listWidth = Math.min(45, Math.max(30, Math.floor(width * 0.4)));
  const detailWidth = memoryDetailWidth(width, listWidth);

  const renderItem = (fact: Fact, ctx: RenderItemContext) => {
    const textWidth = listWidth - 4;
    const tagColor = ctx.isSelected ? colors.text.secondary : colors.text.disabled;
    const expired = fact.expires_at ? new Date(fact.expires_at).getTime() <= Date.now() : false;
    const status =
      fact.archived_at ? "arch" :
      fact.superseded_by_fact_id ? "sup" :
      expired ? "exp" :
      fact.pinned_at ? "pin" :
      "act";
    const review = reviewMarkers?.get(fact.id);
    const lifetime = fact.lifetime === "temporary" && fact.expires_at
      ? `temporary:${formatCountdown(fact.expires_at)}`
      : fact.lifetime;
    const meta = review
      ? reviewLabel(review)
      : `${fact.kind} · ${lifetime} · ${fact.source_type} · importance ${fact.salience}/2 · ${status} · ${shortTime(fact.created_at)}`;

    return (
      <box flexDirection="column" marginBottom={1}>
        <text>
          <span fg={ctx.colors.text}>{truncateText(fact.text, textWidth)}</span>
        </text>
        <text>
          <span fg={review ? colors.status.warning : tagColor}>{truncateText(meta, textWidth)}</span>
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
