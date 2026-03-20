import React from "react";
import { SectionHeader, D, S, formatTokens, formatCost, type UsageData } from "./shared.js";

export function UsageSection({ usage }: { usage: UsageData }) {
  const totalInput = usage.prompt + usage.cache_read + usage.cache_write;
  const hasData = totalInput > 0 || usage.completion > 0;

  const hasCache = usage.cache_read > 0 || usage.cache_write > 0;
  const cachePct = totalInput > 0 ? Math.round((usage.cache_read / totalInput) * 100) : 0;
  const fg = hasData ? S() : D();

  return (
    <box flexDirection="column">
      <SectionHeader label="USAGE" />
      <text>
        <span fg={fg}>{formatTokens(totalInput)}</span>
        <span fg={D()}> ↑ </span>
        <span fg={fg}>{formatTokens(usage.completion)}</span>
        <span fg={D()}> ↓</span>
        {hasCache && <span fg={D()}>  {cachePct}% cache</span>}
      </text>
      <text>
        <span fg={fg}>{hasData ? formatCost(usage.cost) : formatCost(0)}</span>
        {usage.lastCost > 0 && <span fg={D()}>{` (+${formatCost(usage.lastCost)})`}</span>}
      </text>
    </box>
  );
}
