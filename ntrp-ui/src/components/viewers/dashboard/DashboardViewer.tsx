import { useCallback } from "react";
import type { Config } from "../../../types.js";
import { useKeypress, type Key } from "../../../hooks/index.js";
import { useDashboard } from "../../../hooks/useDashboard.js";
import { Dialog, Loading, colors, Hints } from "../../ui/index.js";
import { SystemPanel } from "./SystemPanel.js";
import { AgentPanel } from "./AgentPanel.js";
import { BackgroundPanel } from "./BackgroundPanel.js";

interface DashboardViewerProps {
  config: Config;
  onClose: () => void;
}

const B = colors.text.disabled;
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
  const { data, loading, refresh } = useDashboard(config);

  const handleKeypress = useCallback(
    (key: Key) => {
      if (key.name === "r") { refresh(); return; }
      if (key.name === "escape" || key.name === "q") { onClose(); return; }
    },
    [onClose, refresh]
  );

  useKeypress(handleKeypress, { isActive: true });

  if (loading || !data) {
    return (
      <Dialog title="DASHBOARD" size="large" onClose={onClose}>
        {() => <Loading message="Loading dashboard..." />}
      </Dialog>
    );
  }

  return (
    <Dialog
      title="DASHBOARD"
      size="large"
      onClose={onClose}
      footer={<Hints items={[["r", "refresh"], ["esc", "close"]]} />}
    >
      {({ width, height }) => {
        const colWidth = Math.floor((width - COL_GAP) / 2);
        const totalWidth = colWidth * 2 + COL_GAP;

        return (
          <box flexDirection="column" height={height} overflow="hidden">
            <box flexDirection="row">
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

            <box flexDirection="column" marginTop={1}>
              <Section title="BACKGROUND" width={totalWidth}>
                <BackgroundPanel data={data} width={totalWidth - 4} />
              </Section>
            </box>
          </box>
        );
      }}
    </Dialog>
  );
}
