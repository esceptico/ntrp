import React from "react";
import { SectionHeader, D, S, formatTokens, formatCost, type UsageData } from "./shared.js";

export function UsageSection({ usage }: { usage: UsageData }) {
  const totalInput = usage.prompt + usage.cache_read + usage.cache_write;
  const hasCache = usage.cache_read > 0 || usage.cache_write > 0;
  const cachePct = totalInput > 0 ? Math.round((usage.cache_read / totalInput) * 100) : 0;

  return (
    <box flexDirection="column">
      <SectionHeader label="USAGE" />
      <text>
        <span fg={S}>{formatTokens(totalInput)}</span>
        <span fg={D}> ↑ </span>
        <span fg={S}>{formatTokens(usage.completion)}</span>
        <span fg={D}> ↓</span>
        {hasCache && <span fg={D}>  {cachePct}% cache</span>}
      </text>
      {usage.cost > 0 && (
        <text>
          <span fg={S}>{formatCost(usage.cost)}</span>
          {usage.lastCost > 0 && <span fg={D}>{` (+${formatCost(usage.lastCost)})`}</span>}
        </text>
      )}
    </box>
  );
}
