import type { MemoryPruneCandidate, MemoryPruneDryRun } from "../../../api/client.js";
import { colors, truncateText, type RenderItemContext } from "../../ui/index.js";
import { useAccentColor } from "../../../hooks/index.js";
import { formatTimeAgo, shortTime } from "../../../lib/format.js";
import type { PruneTabState } from "../../../hooks/usePruneTab.js";
import { ListDetailSection, memoryDetailWidth } from "./ListDetailSection.js";

interface PruneSectionProps {
  tab: PruneTabState;
  dryRun: MemoryPruneDryRun | null;
  height: number;
  width: number;
}

function PruneDetails({
  tab,
  dryRun,
  candidate,
  width,
  height,
}: {
  tab: PruneTabState;
  dryRun: MemoryPruneDryRun | null;
  candidate: MemoryPruneCandidate | null;
  width: number;
  height: number;
}) {
  const { accentValue } = useAccentColor();
  const textWidth = Math.max(10, width - 2);

  if (!dryRun) {
    return <text><span fg={colors.text.muted}>No prune dry-run loaded</span></text>;
  }

  return (
    <box flexDirection="column" width={width} height={height} paddingLeft={1} overflow="hidden">
      <text>
        <span fg={accentValue}>cleanup candidates</span>
        <span fg={colors.text.disabled}> {"\u2502"} older than {dryRun.criteria.older_than_days}d</span>
        <span fg={colors.text.disabled}> {"\u2502"} support {"<="} {dryRun.criteria.max_sources}</span>
      </text>
      <box marginTop={1}>
        <text>
          <span fg={colors.text.secondary}>{dryRun.summary.total} matching patterns</span>
          <span fg={colors.text.disabled}> {"\u2502"} {dryRun.summary.empty_sources} no sources</span>
          <span fg={colors.text.disabled}> {"\u2502"} {dryRun.summary.over_1000_chars} long</span>
        </text>
      </box>

      {candidate ? (
        <>
          <box marginTop={2}>
            <text><span fg={colors.text.primary}>{truncateText(candidate.summary, textWidth)}</span></text>
          </box>
          <box marginTop={1} flexDirection="column">
            <text>
              <span fg={colors.text.muted}>archive candidate</span>
              <span fg={colors.text.disabled}> {"\u2502"} {candidate.reason}</span>
            </text>
            <text>
              <span fg={colors.text.disabled}>created {formatTimeAgo(candidate.created_at)}</span>
              <span fg={colors.text.disabled}> {"\u2502"} updated {formatTimeAgo(candidate.updated_at)}</span>
            </text>
            <text>
              <span fg={colors.text.disabled}>{candidate.evidence_count} facts</span>
              <span fg={colors.text.disabled}> {"\u2502"} {"\u00D7"}{candidate.access_count}</span>
              <span fg={colors.text.disabled}> {"\u2502"} {candidate.chars} chars</span>
            </text>
          </box>
          <box marginTop={2}>
            {tab.confirmApply === "selected" ? (
              <text>
                <span fg={accentValue}>archive this candidate?</span>
                <span fg={colors.text.disabled}> y confirm / any cancel</span>
              </text>
            ) : tab.confirmApply === "all" ? (
              <text>
                <span fg={accentValue}>archive all {dryRun.summary.total} matching candidates?</span>
                <span fg={colors.text.disabled}> y confirm / any cancel</span>
              </text>
            ) : (
              <text><span fg={colors.text.disabled}>a archives selected · A archives all matching</span></text>
            )}
          </box>
        </>
      ) : (
        <box marginTop={2}>
          <text><span fg={colors.text.muted}>No matching prune candidates</span></text>
        </box>
      )}
    </box>
  );
}

export function PruneSection({ tab, dryRun, height, width }: PruneSectionProps) {
  const { accentValue } = useAccentColor();
  const listWidth = Math.min(45, Math.max(30, Math.floor(width * 0.4)));
  const detailWidth = memoryDetailWidth(width, listWidth);

  const renderItem = (candidate: MemoryPruneCandidate, ctx: RenderItemContext) => {
    const textWidth = listWidth - 4;
    const tagColor = ctx.isSelected ? colors.text.secondary : colors.text.disabled;

    return (
      <box flexDirection="column" marginBottom={1}>
        <text>
          <span fg={ctx.colors.text}>{truncateText(candidate.summary, textWidth)}</span>
        </text>
        <text>
          <span fg={ctx.isSelected ? accentValue : tagColor}>{candidate.evidence_count} facts</span>
          <span fg={tagColor}> · {candidate.chars} chars</span>
          <span fg={tagColor}> · {shortTime(candidate.created_at)}</span>
        </text>
      </box>
    );
  };

  return (
    <ListDetailSection
      items={tab.filteredCandidates}
      selectedIndex={tab.selectedIndex}
      renderItem={renderItem}
      getKey={(candidate) => candidate.id}
      emptyMessage="No prune candidates"
      searchQuery={tab.searchQuery}
      searchMode={tab.searchMode}
      focusPane={tab.focusPane}
      height={height}
      width={width}
      itemHeight={3}
      onItemClick={tab.setSelectedIndex}
      totalCount={dryRun?.summary.total}
      details={
        <PruneDetails
          tab={tab}
          dryRun={dryRun}
          candidate={tab.selectedCandidate}
          width={detailWidth}
          height={height}
        />
      }
    />
  );
}
