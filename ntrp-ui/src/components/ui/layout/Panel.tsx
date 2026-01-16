import React from "react";
import { Box, Text } from "ink";
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
    <Box flexDirection="column" width={effectiveWidth} paddingX={1} paddingY={1}>
      {title && (
        <Box marginBottom={1}>
          <Text color={accentValue} bold>
            {title}
            {subtitle && <Text color={colors.panel.subtitle}> {subtitle}</Text>}
          </Text>
        </Box>
      )}
      {children}
    </Box>
  );
}
