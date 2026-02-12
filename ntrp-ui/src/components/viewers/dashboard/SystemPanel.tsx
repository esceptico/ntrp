import type { DashboardOverview } from "../../../api/client.js";
import { colors } from "../../ui/colors.js";

interface SystemPanelProps {
  data: DashboardOverview;
  width: number;
}

const B = colors.text.disabled;

const SPARK_CHARS = "▁▂▃▄▅▆▇█";

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return `${n}`;
}

function sparkline(data: number[]): string {
  const max = Math.max(...data);
  if (max === 0) return SPARK_CHARS[0].repeat(data.length);
  return data.map((v) => SPARK_CHARS[Math.min(Math.round((v / max) * 7), 7)]).join("");
}

export function SystemPanel({ data, width }: SystemPanelProps) {
  const { system, tokens } = data;
  const sparkData = tokens.history.map((h) => h.prompt + h.completion);
  const sparkW = Math.min(width - 10, 20);

  return (
    <box flexDirection="column" marginTop={1}>
      <box flexDirection="row">
        <box width={9} flexShrink={0}><text><span fg={B}>uptime</span></text></box>
        <text><span fg={colors.text.primary}>[{formatUptime(system.uptime_seconds)}]</span></text>
      </box>
      <box flexDirection="row">
        <box width={9} flexShrink={0}><text><span fg={B}>model</span></text></box>
        <text><span fg={colors.status.success}>{system.model}</span></text>
      </box>

      <box flexDirection="row" marginTop={1}>
        <box width={9} flexShrink={0}><text><span fg={B}>tokens</span></text></box>
        <text><span fg={B}>{"↑ "}</span></text>
        <text><span fg={colors.text.primary}><strong>{formatTokens(tokens.total_prompt)}</strong></span></text>
        <text>{"   "}</text>
        <text><span fg={B}>{"↓ "}</span></text>
        <text><span fg={colors.text.primary}><strong>{formatTokens(tokens.total_completion)}</strong></span></text>
      </box>
      {sparkData.length > 1 && (
        <box flexDirection="row">
          <box width={9} flexShrink={0}><text><span fg={B}>trend</span></text></box>
          <text><span fg={colors.status.success}>{sparkline(sparkData.slice(-sparkW))}</span></text>
        </box>
      )}

      {Object.keys(system.source_errors).length > 0 && (
        <box flexDirection="row" marginTop={1}>
          {Object.entries(system.source_errors).map(([k, v]) => (
            <text key={k}><span fg={colors.status.error}>{k}: {v} </span></text>
          ))}
        </box>
      )}
    </box>
  );
}
