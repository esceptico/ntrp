import React, { useCallback } from "react";
import { Box, Text } from "ink";
import type { Config } from "../../../types.js";
import { useKeypress, type Key } from "../../../hooks/index.js";
import { useDashboard } from "../../../hooks/useDashboard.js";
import { useDimensions } from "../../../contexts/index.js";
import { Loading, colors } from "../../ui/index.js";
import { SystemPanel } from "./SystemPanel.js";
import { AgentPanel } from "./AgentPanel.js";
import { BackgroundPanel } from "./BackgroundPanel.js";

interface DashboardViewerProps {
  config: Config;
  onClose: () => void;
}

const B = colors.text.disabled;
const MAX_WIDTH = 100;
const COL_GAP = 3;

function Section({ title, width, grow, children }: { title: string; width: number; grow?: boolean; children: React.ReactNode }) {
  const lineLen = Math.max(0, width - title.length - 4);
  return (
    <Box flexDirection="column" flexGrow={grow ? 1 : 0}>
      <Text color={B}>
        ╭ <Text color={colors.text.muted} bold>{title}</Text> {"─".repeat(lineLen)}╮
      </Text>
      <Box flexDirection="column" paddingX={2} flexGrow={grow ? 1 : 0}>
        {children}
      </Box>
      <Text color={B}>╰{" ".repeat(Math.max(0, width - 2))}╯</Text>
    </Box>
  );
}

export function DashboardViewer({ config, onClose }: DashboardViewerProps) {
  const { width: terminalWidth } = useDimensions();
  const w = Math.min(terminalWidth, MAX_WIDTH);
  const colWidth = Math.floor((w - 6 - COL_GAP) / 2);
  const totalWidth = colWidth * 2 + COL_GAP; // exact width all sections share

  const { data, loading, refresh } = useDashboard(config);

  const handleKeypress = useCallback(
    (key: Key) => {
      if (key.name === "r") { refresh(); return; }
      if (key.name === "escape" || key.name === "q") { onClose(); return; }
    },
    [onClose, refresh]
  );

  useKeypress(handleKeypress, { isActive: true });

  if (loading || !data) return <Loading message="Loading dashboard..." />;

  return (
    <Box flexDirection="column" width={w}>
      {/* Top corners */}
      <Box justifyContent="space-between" width={w}>
        <Text color={B}>╭───</Text>
        <Text color={B}>───╮</Text>
      </Box>

      {/* Content */}
      <Box flexDirection="column" paddingX={3}>
        {/* Header */}
        <Box justifyContent="space-between">
          <Text>
            <Text color={colors.status.success} bold>ntrp</Text>
            <Text color={B}> ▸ </Text>
            <Text color={colors.text.primary}>dashboard</Text>
          </Text>
          <Text color={B}>r refresh · esc close</Text>
        </Box>

        {/* System + Agent columns */}
        <Box marginTop={1}>
          <Box flexDirection="column" width={colWidth} marginRight={COL_GAP}>
            <Section title="SYSTEM" width={colWidth} grow>
              <SystemPanel data={data} width={colWidth - 4} />
            </Section>
          </Box>
          <Box flexDirection="column" width={colWidth}>
            <Section title="AGENT" width={colWidth} grow>
              <AgentPanel data={data} width={colWidth - 4} />
            </Section>
          </Box>
        </Box>

        {/* Background */}
        <Box flexDirection="column" marginTop={1}>
          <Section title="BACKGROUND" width={totalWidth}>
            <BackgroundPanel data={data} width={totalWidth - 4} />
          </Section>
        </Box>
      </Box>

      {/* Bottom corners */}
      <Box justifyContent="space-between" width={w}>
        <Text color={B}>╰───</Text>
        <Text color={B}>───╯</Text>
      </Box>
    </Box>
  );
}
