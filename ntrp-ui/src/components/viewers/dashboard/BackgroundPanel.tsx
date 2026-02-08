import React from "react";
import { Box, Text } from "ink";
import type { DashboardOverview } from "../../../api/client.js";
import { colors } from "../../ui/colors.js";

interface BackgroundPanelProps {
  data: DashboardOverview;
  width: number;
}

const B = colors.text.disabled;

function relativeTime(ts: number): string {
  const diff = Math.floor(Date.now() / 1000 - ts);
  if (diff < 5) return "just now";
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

type Status = "ok" | "active" | "error" | "idle";

function pillColor(s: Status): string {
  switch (s) {
    case "ok": return colors.status.success;
    case "active": return colors.status.warning;
    case "error": return colors.status.error;
    case "idle": return B;
  }
}

export function BackgroundPanel({ data, width }: BackgroundPanelProps) {
  const { background, memory } = data;
  const { indexer, scheduler, consolidation } = background;

  const idxStatus: Status = indexer.status === "done" ? "ok"
    : indexer.status === "indexing" ? "active"
    : indexer.status === "error" ? "error"
    : "idle";

  return (
    <Box flexDirection="column" marginTop={1}>
      <Box>
        <Text color={B}>{"indexer".padEnd(18)}</Text>
        <Text color={pillColor(idxStatus)}>[{idxStatus}]</Text>
        {indexer.status === "indexing" && (
          <Text color={B}> {indexer.progress_done}/{indexer.progress_total}</Text>
        )}
        {indexer.error && <Text color={colors.status.error}> {indexer.error}</Text>}
      </Box>
      <Box>
        <Text color={B}>{"scheduler".padEnd(18)}</Text>
        <Text color={pillColor(scheduler.running ? "active" : "idle")}>
          [{scheduler.running ? "active" : "idle"}]
        </Text>
        {scheduler.enabled_count > 0 && (
          <Text color={B}> {scheduler.enabled_count} tasks</Text>
        )}
        {scheduler.next_run_at && (
          <Text color={B}> · next {formatTime(scheduler.next_run_at)}</Text>
        )}
      </Box>
      {scheduler.active_task && (
        <Box marginLeft={18}>
          <Text color={colors.status.warning}>→ {scheduler.active_task}</Text>
        </Box>
      )}
      <Box>
        <Text color={B}>{"consolidation".padEnd(18)}</Text>
        <Text color={pillColor(consolidation.running ? "active" : "idle")}>
          [{consolidation.running ? "active" : "idle"}]
        </Text>
        {memory.unconsolidated > 0 && (
          <Text color={B}> {memory.unconsolidated} pending</Text>
        )}
        {memory.last_consolidation_at && (
          <Text color={B}> · {relativeTime(memory.last_consolidation_at)}</Text>
        )}
      </Box>

      <Box marginTop={1}>
        <Text color={B}>memory  </Text>
        <Text color={colors.text.primary} bold>{memory.fact_count}</Text>
        <Text color={B}> facts   </Text>
        <Text color={colors.text.primary} bold>{memory.link_count}</Text>
        <Text color={B}> links   </Text>
        <Text color={colors.text.primary} bold>{memory.observation_count}</Text>
        <Text color={B}> obs</Text>
      </Box>

      {memory.recent_facts.length > 0 && (
        <Box flexDirection="column" marginTop={1}>
          {memory.recent_facts.map((fact) => (
            <Box key={fact.id}>
              <Text color={B}>{relativeTime(fact.ts).padEnd(10)}</Text>
              <Text color={colors.text.muted}>{fact.text}</Text>
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );
}
