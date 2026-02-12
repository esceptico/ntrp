import React from "react";
import { useDimensions } from "../../../contexts/index.js";
import { colors } from "../colors.js";

interface SplitViewProps {
  sidebarWidth: number;
  sidebar: React.ReactNode;
  main: React.ReactNode;
  divider?: boolean;
  width?: number;
  height?: number;
}

export function SplitView({ sidebarWidth, sidebar, main, divider = true, width, height }: SplitViewProps) {
  const { width: terminalWidth } = useDimensions();
  const totalWidth = width ?? terminalWidth;
  const dividerWidth = divider ? 1 : 0;
  const mainWidth = Math.max(0, totalWidth - sidebarWidth - dividerWidth);

  return (
    <box flexDirection="row" width={totalWidth} height={height}>
      <box width={sidebarWidth} height={height} flexShrink={0} overflow="hidden">
        {sidebar}
      </box>
      {divider && (
        <box width={1} height={height} flexShrink={0} flexDirection="column">
          {height ? (
            Array.from({ length: height }).map((_, i) => (
              <text key={i}><span fg={colors.divider}>{"\u2502"}</span></text>
            ))
          ) : (
            <text><span fg={colors.divider}>{"\u2502"}</span></text>
          )}
        </box>
      )}
      <box width={mainWidth} height={height} overflow="hidden">
        {main}
      </box>
    </box>
  );
}
