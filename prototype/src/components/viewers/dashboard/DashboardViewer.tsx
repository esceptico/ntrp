import { useCallback } from "react";
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
    <box flexDirection="column" flexGrow={grow ? 1 : 0}>
      <text>
        <span fg={B}>╭ </span>
        <span fg={colors.text.muted}><strong>{title}</strong></span>
        <span fg={B}> {"─".repeat(lineLen)}╮</span>
      </text>
      <box flexDirection="column" paddingX={2} flexGrow={grow ? 1 : 0}>
        {children}
      </box>
      <text><span fg={B}>╰{" ".repeat(Math.max(0, width - 2))}╯</span></text>
    </box>
  );
}

export function DashboardViewer({ config, onClose }: DashboardViewerProps) {
  const { width: terminalWidth } = useDimensions();
  const w = Math.min(terminalWidth, MAX_WIDTH);
  const colWidth = Math.floor((w - 6 - COL_GAP) / 2);
  const totalWidth = colWidth * 2 + COL_GAP;

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
    <box flexDirection="column" width={w}>
      {/* Top corners */}
      <box justifyContent="space-between" width={w}>
        <text><span fg={B}>╭───</span></text>
        <text><span fg={B}>───╮</span></text>
      </box>

      {/* Content */}
      <box flexDirection="column" paddingX={3}>
        {/* Header */}
        <box justifyContent="space-between">
          <text>
            <span fg={colors.status.success}><strong>ntrp</strong></span>
            <span fg={B}> ▸ </span>
            <span fg={colors.text.primary}>dashboard</span>
          </text>
          <text><span fg={B}>r refresh · esc close</span></text>
        </box>

        {/* System + Agent columns */}
        <box marginTop={1}>
          <box flexDirection="column" width={colWidth} marginRight={COL_GAP}>
            <Section title="SYSTEM" width={colWidth} grow>
              <SystemPanel data={data} width={colWidth - 4} />
            </Section>
          </box>
          <box flexDirection="column" width={colWidth}>
            <Section title="AGENT" width={colWidth} grow>
              <AgentPanel data={data} width={colWidth - 4} />
            </Section>
          </box>
        </box>

        {/* Background */}
        <box flexDirection="column" marginTop={1}>
          <Section title="BACKGROUND" width={totalWidth}>
            <BackgroundPanel data={data} width={totalWidth - 4} />
          </Section>
        </box>
      </box>

      {/* Bottom corners */}
      <box justifyContent="space-between" width={w}>
        <text><span fg={B}>╰───</span></text>
        <text><span fg={B}>───╯</span></text>
      </box>
    </box>
  );
}
