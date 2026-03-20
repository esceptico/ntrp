import React from "react";
import { colors } from "../ui/colors.js";
import type { SidebarData } from "../../hooks/useSidebar.js";
import { SectionHeader, D, S, formatTokens } from "./shared.js";

function ContextBar({ total, limit, width }: { total: number | null; limit: number; width: number }) {
  if (!total || !limit) {
    return <text><span fg={D()}>no context</span></text>;
  }

  const pct = Math.min(1, total / limit);
  const barWidth = Math.max(4, width - 5);
  const filled = Math.round(pct * barWidth);
  const empty = barWidth - filled;
  const pctStr = `${Math.round(pct * 100)}%`;

  const barColor = pct > 0.8 ? colors.status.error : pct > 0.5 ? colors.status.warning : colors.status.success;

  return (
    <text>
      <span fg={barColor}>{"\u2588".repeat(filled)}</span>
      <span fg={colors.border}>{"\u2591".repeat(empty)}</span>
      <span fg={S()}> {pctStr}</span>
    </text>
  );
}

export function ContextSection({ context, width }: { context: NonNullable<SidebarData["context"]>; width: number }) {
  return (
    <box flexDirection="column">
      <SectionHeader label="CONTEXT" />
      <ContextBar total={context.total} limit={context.limit} width={width} />
      <text>
        <span fg={D()}>{formatTokens(context.total)} / {formatTokens(context.limit)}</span>
      </text>
      <text>
        <span fg={D()}>{context.message_count} msgs  {context.tool_count} tools</span>
      </text>
    </box>
  );
}
