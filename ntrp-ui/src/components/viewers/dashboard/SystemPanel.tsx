import { Box, Text } from "ink";
import type { DashboardOverview } from "../../../api/client.js";
import { colors } from "../../ui/colors.js";
import { Sparkline } from "@pppp606/ink-chart";

interface SystemPanelProps {
  data: DashboardOverview;
  width: number;
}

const B = colors.text.disabled;

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

export function SystemPanel({ data, width }: SystemPanelProps) {
  const { system, tokens } = data;
  const sparkData = tokens.history.map((h) => h.prompt + h.completion);
  const sparkW = Math.min(width - 10, 20);

  return (
    <Box flexDirection="column" marginTop={1}>
      <Box>
        <Box width={9} flexShrink={0}><Text color={B}>uptime</Text></Box>
        <Text color={colors.text.primary}>[{formatUptime(system.uptime_seconds)}]</Text>
      </Box>
      <Box>
        <Box width={9} flexShrink={0}><Text color={B}>model</Text></Box>
        <Text color={colors.status.success}>{system.model}</Text>
      </Box>

      <Box marginTop={1}>
        <Box width={9} flexShrink={0}><Text color={B}>tokens</Text></Box>
        <Text color={B}>↑ </Text>
        <Text color={colors.text.primary} bold>{formatTokens(tokens.total_prompt)}</Text>
        <Text>   </Text>
        <Text color={B}>↓ </Text>
        <Text color={colors.text.primary} bold>{formatTokens(tokens.total_completion)}</Text>
      </Box>
      {sparkData.length > 1 && (
        <Box>
          <Box width={9} flexShrink={0}><Text color={B}>trend</Text></Box>
          <Sparkline data={sparkData.slice(-sparkW)} width={sparkW} colorScheme="green" />
        </Box>
      )}

      {Object.keys(system.source_errors).length > 0 && (
        <Box marginTop={1}>
          {Object.entries(system.source_errors).map(([k, v]) => (
            <Text key={k} color={colors.status.error}>{k}: {v} </Text>
          ))}
        </Box>
      )}
    </Box>
  );
}
