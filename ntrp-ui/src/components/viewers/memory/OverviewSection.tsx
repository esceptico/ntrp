import type { Fact, MemoryEvent, MemoryPruneDryRun } from "../../../api/client.js";
import { colors } from "../../ui/index.js";
import { useAccentColor } from "../../../hooks/index.js";
import { formatTimeAgo } from "../../../lib/format.js";

interface OverviewSectionProps {
  profileFacts: Fact[];
  factTotal: number;
  observationTotal: number;
  pruneDryRun: MemoryPruneDryRun | null;
  memoryEvents: MemoryEvent[];
  height: number;
  width: number;
}

function MetricRow({ label, value, note }: { label: string; value: string | number; note: string }) {
  return (
    <text>
      <span fg={colors.text.secondary}>{label}</span>
      <span fg={colors.text.disabled}> {"\u2502"} </span>
      <span fg={colors.text.primary}>{value}</span>
      <span fg={colors.text.disabled}> {"\u2502"} {note}</span>
    </text>
  );
}

export function OverviewSection({
  profileFacts,
  factTotal,
  observationTotal,
  pruneDryRun,
  memoryEvents,
  height,
  width,
}: OverviewSectionProps) {
  const { accentValue } = useAccentColor();
  const latestEvent = memoryEvents[0];

  return (
    <box flexDirection="column" width={width} height={height} paddingLeft={1} overflow="hidden">
      <text>
        <span fg={accentValue}>memory overview</span>
        <span fg={colors.text.disabled}> {"\u2502"} current health and control surface</span>
      </text>

      <box flexDirection="column" marginTop={2}>
        <MetricRow label="Profile" value={profileFacts.length} note="always-on facts shown to the agent first" />
        <MetricRow label="Facts" value={factTotal} note="source-of-truth memory records" />
        <MetricRow label="Patterns" value={observationTotal} note="derived summaries with supporting facts" />
        <MetricRow
          label="Cleanup"
          value={pruneDryRun?.summary.total ?? 0}
          note="archive candidates matching the current cleanup rule"
        />
        <MetricRow label="Log" value={memoryEvents.length} note="recent memory writes and automation outcomes loaded" />
      </box>

      <box flexDirection="column" marginTop={2}>
        <text><span fg={colors.text.muted}>OPEN NEXT</span></text>
        <text><span fg={colors.text.secondary}>Profile</span><span fg={colors.text.disabled}> for what the agent should always know</span></text>
        <text><span fg={colors.text.secondary}>Facts</span><span fg={colors.text.disabled}> to edit durable truth</span></text>
        <text><span fg={colors.text.secondary}>Patterns</span><span fg={colors.text.disabled}> to inspect derived memory and provenance</span></text>
        <text><span fg={colors.text.secondary}>Cleanup</span><span fg={colors.text.disabled}> to archive low-value patterns in bulk</span></text>
        <text><span fg={colors.text.secondary}>Log</span><span fg={colors.text.disabled}> to answer why memory changed</span></text>
      </box>

      <box flexDirection="column" marginTop={2}>
        <text><span fg={colors.text.muted}>LATEST</span></text>
        {latestEvent ? (
          <text>
            <span fg={colors.text.secondary}>{latestEvent.action}</span>
            <span fg={colors.text.disabled}> {"\u2502"} {latestEvent.actor}</span>
            <span fg={colors.text.disabled}> {"\u2502"} {formatTimeAgo(latestEvent.created_at)}</span>
          </text>
        ) : (
          <text><span fg={colors.text.disabled}>No memory log entries loaded</span></text>
        )}
      </box>
    </box>
  );
}
