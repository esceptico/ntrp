import React from "react";
import { truncateText } from "../../lib/utils.js";
import type { Automation } from "../../api/client.js";
import { SectionHeader, D, S } from "./shared.js";

function formatRelativeTime(isoStr: string): string {
  const target = new Date(isoStr).getTime();
  const now = Date.now();
  const diff = target - now;

  if (diff < 0) return "now";

  const mins = Math.floor(diff / 60_000);
  if (mins < 60) return `${mins}m`;

  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;

  const days = Math.floor(hours / 24);
  return `${days}d`;
}

function AutomationRow({ automation, width }: { automation: Automation; width: number }) {
  const time = automation.trigger.type === "time"
    ? (() => {
        let base = automation.trigger.every ? `every ${automation.trigger.every}` : automation.trigger.at ?? "";
        if (automation.trigger.start && automation.trigger.end) base += ` (${automation.trigger.start}\u2013${automation.trigger.end})`;
        return base;
      })()
    : `on:${automation.trigger.event_type}`;
  const eta = automation.next_run_at ? formatRelativeTime(automation.next_run_at) : "";
  const prefix = `${time} `;
  const suffix = eta ? ` ${eta}` : "";
  const nameWidth = Math.max(4, width - prefix.length - suffix.length);
  const name = truncateText(automation.name || automation.description, nameWidth);

  return (
    <text>
      <span fg={D}>{prefix}</span>
      <span fg={S}>{name}</span>
      {suffix && <span fg={D}>{suffix}</span>}
    </text>
  );
}

export function AutomationsSection({ automations, width }: { automations: Automation[]; width: number }) {
  return (
    <box flexDirection="column">
      <SectionHeader label="NEXT UP" />
      {automations.map(s => (
        <AutomationRow key={s.task_id} automation={s} width={width} />
      ))}
    </box>
  );
}
