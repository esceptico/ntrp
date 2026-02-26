import type { Automation } from "../../../api/client.js";
import { colors, truncateText, type RenderItemContext } from "../../ui/index.js";
import { formatRelativeTime } from "../../../lib/format.js";

interface AutomationItemProps {
  item: Automation;
  context: RenderItemContext;
  textWidth: number;
}

function triggerLabel(trigger: Automation["trigger"]): string {
  switch (trigger.type) {
    case "time": {
      let base = trigger.every ? `every ${trigger.every}` : trigger.at ?? "";
      if (trigger.start && trigger.end) base += ` (${trigger.start}\u2013${trigger.end})`;
      return trigger.days ? `${base}  ${trigger.days}` : base;
    }
    case "event": return `on:${trigger.event_type}`;
  }
}

// Fixed 3-line layout: status+meta, description, timing
export function AutomationItem({ item, context, textWidth }: AutomationItemProps) {
  const enabled = item.enabled;
  const isRunning = !!item.running_since;
  const statusIcon = isRunning ? "\u25B6" : enabled ? "\u2713" : "\u23F8";
  const statusColor = isRunning
    ? colors.tool.running
    : enabled
      ? colors.status.success
      : colors.text.disabled;
  const textColor = context.isSelected
    ? colors.text.primary
    : enabled
      ? colors.text.secondary
      : colors.text.disabled;
  const metaColor = context.isSelected ? colors.text.secondary : colors.text.muted;

  const nextRun = enabled ? formatRelativeTime(item.next_run_at) : "disabled";
  const lastRun = formatRelativeTime(item.last_run_at);

  return (
    <box flexDirection="column" marginBottom={1}>
      <text>
        <span fg={statusColor}>{statusIcon}</span>
        <span fg={metaColor}>{` ${triggerLabel(item.trigger)}${item.writable ? "  \u270E" : ""}${item.notifiers.length > 0 ? `  \u2192 ${item.notifiers.join(", ")}` : ""}`}</span>
      </text>
      {item.name
        ? <text><strong><span fg={textColor}>{item.name}</span></strong> <span fg={metaColor}>{truncateText(item.description, textWidth - item.name.length - 1)}</span></text>
        : <text><span fg={textColor}>{truncateText(item.description, textWidth)}</span></text>
      }
      <text><span fg={metaColor}>{`next: ${nextRun}   last: ${lastRun}`}</span></text>
    </box>
  );
}
