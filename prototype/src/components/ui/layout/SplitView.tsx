import React from "react";
import { useDimensions } from "../../../contexts/index.js";
import { colors } from "../colors.js";

interface SplitViewProps {
  sidebarWidth: number;
  sidebar: React.ReactNode;
  main: React.ReactNode;
  divider?: boolean;
}

export function SplitView({ sidebarWidth, sidebar, main, divider = true }: SplitViewProps) {
  const { width: terminalWidth } = useDimensions();
  const dividerWidth = divider ? 1 : 0;
  const mainWidth = Math.max(0, terminalWidth - sidebarWidth - dividerWidth - 2);

  return (
    <box flexDirection="row" width={terminalWidth}>
      <box width={sidebarWidth} flexShrink={0} overflow="hidden">
        {sidebar}
      </box>
      {divider && (
        <box width={1} flexShrink={0}>
          <text><span fg={colors.divider}>{"\u2502"}</span></text>
        </box>
      )}
      <box width={mainWidth} flexGrow={1} overflow="hidden">
        {main}
      </box>
    </box>
  );
}
