import React from "react";
import type { LearningCandidate, Stats } from "../../api/memory.js";
import { useAccentColor } from "../../hooks/index.js";
import { summarizeLearningCandidates } from "../../lib/memoryLearning.js";
import { truncateText } from "../../lib/utils.js";
import { colors } from "../ui/colors.js";
import { SectionHeader, D, S } from "./shared.js";

interface MemorySectionProps {
  stats: Stats | null;
  learningCandidates: LearningCandidate[];
  width: number;
}

function formatCount(value: number): string {
  if (value >= 1000) return `${(value / 1000).toFixed(1)}k`;
  return String(value);
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
  const { accentValue } = useAccentColor();
  const summary = summarizeLearningCandidates(learningCandidates);
  const notificationColor = summary.needsAction > 0 ? colors.status.warning : colors.status.success;
  const notification =
    summary.needsAction > 0
      ? `${summary.proposed} review · ${summary.readyToApply} apply`
      : summary.active > 0
        ? `${summary.active} active · clean`
        : "clean";
  const laneLine = laneSummary(summary);

  return (
    <box flexDirection="column">
      <SectionHeader label="MEMORY" />
      {stats && (
        <text>
          <span fg={S()}>{formatCount(stats.fact_count)}</span>
          <span fg={D()}> facts · </span>
          <span fg={S()}>{formatCount(stats.observation_count)}</span>
          <span fg={D()}> patterns</span>
        </text>
      )}
      <text>
        <span fg={summary.needsAction > 0 ? accentValue : notificationColor}>learn </span>
        <span fg={summary.needsAction > 0 ? colors.text.secondary : D()}>
          {truncateText(notification, Math.max(8, width - 6))}
        </span>
      </text>
      {laneLine && (
        <text>
          <span fg={D()}>{truncateText(laneLine, width)}</span>
        </text>
      )}
    </box>
  );
}
