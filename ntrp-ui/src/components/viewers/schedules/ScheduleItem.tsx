import { Box, Text } from "ink";
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
  const statusIcon = isRunning ? "▶" : enabled ? "✓" : "⏸";
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
    <Box flexDirection="column" marginBottom={1}>
      <Text>
        <Text color={statusColor}>{statusIcon}</Text>
        <Text color={metaColor}>{` ${item.time_of_day}  ${item.recurrence}${item.writable ? "  ✎" : ""}${item.notifiers.length > 0 ? `  → ${item.notifiers.join(", ")}` : ""}`}</Text>
      </Text>
      <Text color={textColor}>{wrapText(item.description, textWidth).join("\n")}</Text>
      <Text color={metaColor}>{`next: ${nextRun}   last: ${lastRun}`}</Text>
    </Box>
  );
}
