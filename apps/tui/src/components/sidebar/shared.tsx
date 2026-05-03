import React from "react";
import { colors } from "../ui/colors.js";
import type { TokenUsage } from "../../types.js";

export type UsageData = TokenUsage;

export function H() { return colors.text.secondary; }
export function D() { return colors.text.disabled; }
export function S() { return colors.text.muted; }

export function SectionHeader({ label }: { label: string }) {
  return (
    <text>
      <span fg={H()}>{label}</span>
    </text>
  );
}

export function formatTokens(total: number | null, pad?: number): string {
  let s: string;
  if (!total) s = "0";
  else if (total >= 1_000_000) s = `${(total / 1_000_000).toFixed(1)}M`;
  else if (total >= 1_000) s = `${(total / 1_000).toFixed(1)}k`;
  else s = `${total}`;
  return pad ? s.padStart(pad) : s;
}

export function formatCost(cost: number): string {
  return `$${cost.toFixed(2)}`;
}
