import React from "react";
import type { LearningCandidate, Stats } from "../../api/memory.js";
import { summarizeLearningCandidates } from "../../lib/memoryLearning.js";
import { truncateText } from "../../lib/utils.js";
import { colors } from "../ui/colors.js";
import { SectionHeader, D, S } from "./shared.js";

interface MemorySectionProps {
  stats: Stats | null;
  learningCandidates: LearningCandidate[];
  width: number;
}

const LABEL_WIDTH = 9;

function formatCount(value: number): string {
  if (value >= 1000) return `${(value / 1000).toFixed(1)}k`;
  return String(value);
}

function MemoryRow({
  label,
  value,
  width,
  valueColor = S(),
}: {
  label: string;
  value: string;
  width: number;
  valueColor?: string;
}) {
  return (
    <text>
      <span fg={D()}>{label.padEnd(LABEL_WIDTH)}</span>
      <span fg={valueColor}>{truncateText(value, Math.max(1, width - LABEL_WIDTH))}</span>
    </text>
  );
}

function laneSummary(summary: ReturnType<typeof summarizeLearningCandidates>): string {
  const parts: Array<[string, number]> = [
    ["mem", summary.needsActionByLane.memory],
    ["run", summary.needsActionByLane.runtime],
    ["skill", summary.needsActionByLane.skill],
    ["auto", summary.needsActionByLane.automation],
  ];

  const activeParts = parts.filter(([, count]) => count > 0);
  if (activeParts.length === 0) return "";
  return activeParts.map(([label, count]) => `${label} ${count}`).join(" · ");
}

export function MemorySection({ stats, learningCandidates, width }: MemorySectionProps) {
  const summary = summarizeLearningCandidates(learningCandidates);
  const laneLine = laneSummary(summary);
  const learningLine =
    summary.needsAction > 0
      ? `${summary.proposed} review · ${summary.readyToApply} apply`
      : summary.active > 0
        ? `${summary.active} active`
        : "clean";

  return (
    <box flexDirection="column">
      <SectionHeader label="MEMORY" />
      {stats && <MemoryRow label="facts" value={formatCount(stats.fact_count)} width={width} />}
      {stats && <MemoryRow label="patterns" value={formatCount(stats.observation_count)} width={width} />}
      <MemoryRow
        label="learning"
        value={learningLine}
        width={width}
        valueColor={summary.needsAction > 0 ? colors.status.warning : S()}
      />
      {laneLine && (
        <MemoryRow label="lanes" value={laneLine} width={width} valueColor={D()} />
      )}
    </box>
  );
}
