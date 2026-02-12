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
    <box flexDirection="column" marginTop={1}>
      {/* Runs */}
      <box flexDirection="row">
        <text><span fg={B}>{"runs "}</span></text>
        <text><span fg={colors.text.primary}><strong>{agent.total_runs}</strong></span></text>
        {agent.active_runs > 0 && (
          <text><span fg={colors.status.warning}>{" "}[{agent.active_runs} active]</span></text>
        )}
      </box>

      {/* Recent tool calls */}
      {recentTools.length > 0 && (
        <box flexDirection="column" marginTop={1}>
          {recentTools.map((tool) => (
            <box flexDirection="row" key={`${tool.name}-${tool.ts}`}>
              <text>
                <span fg={tool.error ? colors.status.error : B}>
                  {tool.error ? "✗" : "·"}
                </span>
              </text>
              <text><span fg={colors.text.secondary}>{" "}{tool.name.padEnd(16)}</span></text>
              <text>
                <span fg={durationColor(tool.duration_ms)}>
                  {formatDuration(tool.duration_ms).padStart(7)}
                </span>
              </text>
              <text><span fg={B}>{" "}{relativeTime(tool.ts).padStart(4)}</span></text>
            </box>
          ))}
        </box>
      )}

      {/* Tool stats */}
      {toolStats.length > 0 && (
        <box flexDirection="column" marginTop={1}>
          <text><span fg={B}>stats</span></text>
          {toolStats.slice(0, 5).map(([name, stats]) => (
            <box flexDirection="row" key={name}>
              <text><span fg={colors.text.muted}>{name.padEnd(16)}</span></text>
              <text><span fg={colors.text.secondary}>{`×${stats.count}`.padStart(4)}</span></text>
              <text><span fg={B}>{" avg "}</span></text>
              <text><span fg={durationColor(stats.avg_ms)}>{formatDuration(stats.avg_ms).padStart(7)}</span></text>
              {stats.error_count > 0 && (
                <text><span fg={colors.status.error}>{" "}{stats.error_count}err</span></text>
              )}
            </box>
          ))}
        </box>
      )}

      {recentTools.length === 0 && (
        <box marginTop={1}>
          <text><span fg={B}>no calls yet</span></text>
        </box>
      )}
    </box>
  );
}
