import React from "react";
import { SectionHeader, D, S, formatTokens, formatCost, type UsageData } from "./shared.js";

export function UsageSection({ usage }: { usage: UsageData }) {
  const totalInput = usage.prompt + usage.cache_read + usage.cache_write;
  const lastInput = usage.lastPrompt + usage.lastCacheRead + usage.lastCacheWrite;
  const hasData = totalInput > 0 || usage.completion > 0;

  const hasCache = usage.cache_read > 0 || usage.cache_write > 0;
  const averageCachePct = totalInput > 0 ? Math.round((usage.cache_read / totalInput) * 100) : 0;
  const lastCachePct = lastInput > 0 ? Math.round((usage.lastCacheRead / lastInput) * 100) : 0;
  const fg = hasData ? S() : D();

  return (
    <box flexDirection="column">
      <SectionHeader label="USAGE" />
      <text>
        <span fg={fg}>{formatTokens(totalInput)}</span>
        <span fg={D()}> ↑ </span>
        <span fg={fg}>{formatTokens(usage.completion)}</span>
        <span fg={D()}> ↓</span>
      </text>
      {hasCache && (
        <text>
          <span fg={D()}>cache </span>
          <span fg={fg}>{lastCachePct}% last</span>
          <span fg={D()}>{` · ${averageCachePct}% avg`}</span>
        </text>
      )}
      <text>
        <span fg={fg}>{hasData ? formatCost(usage.cost) : formatCost(0)}</span>
        {usage.lastCost > 0 && <span fg={D()}>{` (+${formatCost(usage.lastCost)})`}</span>}
      </text>
    </box>
  );
}
