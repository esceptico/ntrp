import React, { memo } from "react";
import { Box, Text } from "ink";
import { colors } from "../../ui/colors.js";
import { useDimensions } from "../../../contexts/index.js";
import { useAccentColor } from "../../../hooks/index.js";

interface ThinkingMessageProps {
  content: string;
}

export const ThinkingMessage = memo(function ThinkingMessage({ content }: ThinkingMessageProps) {
  const { width: terminalWidth } = useDimensions();
  const { accentValue } = useAccentColor();
  const contentWidth = Math.max(0, terminalWidth - 4);

  return (
    <Box flexDirection="column" width={terminalWidth} overflow="hidden">
      <Text>
        <Text color={accentValue}>✻ </Text>
        <Text color={accentValue}>Thinking…</Text>
      </Text>
      {content && (
        <Box marginLeft={2} width={contentWidth} overflow="hidden">
          <Text color={colors.text.secondary} wrap="wrap">{content}</Text>
        </Box>
      )}
    </Box>
  );
});
