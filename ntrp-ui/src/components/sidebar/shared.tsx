import React from "react";
import { colors } from "../ui/colors.js";

export const H = colors.text.secondary;
export const D = colors.text.disabled;
export const S = colors.text.muted;

export function SectionHeader({ label }: { label: string }) {
  return (
    <text>
      <span fg={H}>{label}</span>
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

export interface UsageData {
  prompt: number;
  completion: number;
  cache_read: number;
  cache_write: number;
  cost: number;
  lastCost: number;
}
