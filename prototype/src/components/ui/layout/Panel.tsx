import React from "react";
import { useAccentColor } from "../../../hooks/useAccentColor.js";
import { useContentWidth } from "../../../contexts/index.js";
import { colors } from "../colors.js";

interface PanelProps {
  children: React.ReactNode;
  title?: string;
  subtitle?: string;
  width?: number;
}

export function Panel({ children, title, subtitle, width }: PanelProps) {
  const { accentValue } = useAccentColor();
  const contentWidth = useContentWidth();
  const effectiveWidth = width ?? contentWidth;

  return (
    <box flexDirection="column" width={effectiveWidth} paddingX={1} paddingY={1}>
      {title && (
        <box marginBottom={1}>
          <text>
            <span fg={accentValue}><strong>{title}</strong></span>
            {subtitle && <span fg={colors.panel.subtitle}> {subtitle}</span>}
          </text>
        </box>
      )}
      {children}
    </box>
  );
}
