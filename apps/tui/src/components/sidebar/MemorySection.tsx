import React from "react";
import type { Stats } from "../../api/memory.js";
import { truncateText } from "../../lib/utils.js";
import { SectionHeader, D, S } from "./shared.js";

interface MemorySectionProps {
  stats: Stats | null;
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

export function MemorySection({ stats, width }: MemorySectionProps) {
  return (
    <box flexDirection="column">
      <SectionHeader label="MEMORY" />
      {stats && <MemoryRow label="evidence" value={formatCount(stats.fact_count)} width={width} />}
      {stats && <MemoryRow label="patterns" value={formatCount(stats.observation_count)} width={width} />}
    </box>
  );
}
