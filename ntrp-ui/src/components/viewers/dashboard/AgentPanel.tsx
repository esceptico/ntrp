import React from "react";
import { Box, Text } from "ink";
import type { DashboardOverview } from "../../../api/client.js";
import { colors } from "../../ui/colors.js";

interface AgentPanelProps {
  data: DashboardOverview;
  width: number;
}

const B = colors.text.disabled;

function durationColor(ms: number): string {
  if (ms < 100) return colors.status.success;
  if (ms < 1000) return colors.status.warning;
  return colors.status.error;
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function relativeTime(ts: number): string {
  const diff = Math.floor(Date.now() / 1000 - ts);
  if (diff < 5) return "now";
  if (diff < 60) return `${diff}s`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m`;
  return `${Math.floor(diff / 3600)}h`;
}

export function AgentPanel({ data, width }: AgentPanelProps) {
  const { agent } = data;
  const recentTools = agent.recent_tools.slice(-8).reverse();
  const toolStats = Object.entries(agent.tool_stats).sort(([, a], [, b]) => b.count - a.count);

  return (
    <Box flexDirection="column" marginTop={1}>
      {/* Runs */}
      <Box>
        <Text color={B}>runs </Text>
        <Text color={colors.text.primary} bold>{agent.total_runs}</Text>
        {agent.active_runs > 0 && (
          <Text color={colors.status.warning}> [{agent.active_runs} active]</Text>
        )}
      </Box>

      {/* Recent tool calls */}
      {recentTools.length > 0 && (
        <Box flexDirection="column" marginTop={1}>
          {recentTools.map((tool) => (
            <Box key={`${tool.name}-${tool.ts}`}>
              <Text color={tool.error ? colors.status.error : B}>
                {tool.error ? "✗" : "·"}
              </Text>
              <Text color={colors.text.secondary}> {tool.name.padEnd(16)}</Text>
              <Text color={durationColor(tool.duration_ms)}>
                {formatDuration(tool.duration_ms).padStart(7)}
              </Text>
              <Text color={B}> {relativeTime(tool.ts).padStart(4)}</Text>
            </Box>
          ))}
        </Box>
      )}

      {/* Tool stats */}
      {toolStats.length > 0 && (
        <Box flexDirection="column" marginTop={1}>
          <Text color={B} dimColor>stats</Text>
          {toolStats.slice(0, 5).map(([name, stats]) => (
            <Box key={name}>
              <Text color={colors.text.muted}>{name.padEnd(16)}</Text>
              <Text color={colors.text.secondary}>{`×${stats.count}`.padStart(4)}</Text>
              <Text color={B}> avg </Text>
              <Text color={durationColor(stats.avg_ms)}>{formatDuration(stats.avg_ms).padStart(7)}</Text>
              {stats.error_count > 0 && (
                <Text color={colors.status.error}> {stats.error_count}err</Text>
              )}
            </Box>
          ))}
        </Box>
      )}

      {recentTools.length === 0 && (
        <Box marginTop={1}>
          <Text color={B}>no calls yet</Text>
        </Box>
      )}
    </Box>
  );
}
