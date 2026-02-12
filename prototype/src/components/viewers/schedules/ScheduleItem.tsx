import type { Schedule } from "../../../api/client.js";
import { colors, type RenderItemContext } from "../../ui/index.js";
import { wrapText } from "../../../lib/utils.js";
import { formatRelativeTime } from "../../../lib/format.js";

interface ScheduleItemProps {
  item: Schedule;
  context: RenderItemContext;
  textWidth: number;
}

export function ScheduleItem({ item, context, textWidth }: ScheduleItemProps) {
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
        <span fg={metaColor}>{` ${item.time_of_day}  ${item.recurrence}${item.writable ? "  \u270E" : ""}${item.notifiers.length > 0 ? `  \u2192 ${item.notifiers.join(", ")}` : ""}`}</span>
      </text>
      {item.name ? <text><strong><span fg={textColor}>{item.name}</span></strong></text> : null}
      <text><span fg={item.name ? metaColor : textColor}>{wrapText(item.description, textWidth).join("\n")}</span></text>
      <text><span fg={metaColor}>{`next: ${nextRun}   last: ${lastRun}`}</span></text>
    </box>
  );
}
