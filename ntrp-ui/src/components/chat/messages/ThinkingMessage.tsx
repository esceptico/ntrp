import React, { memo } from "react";
import { Box, Text } from "ink";
import { brand, colors } from "../../ui/colors.js";
import { useDimensions } from "../../../contexts/index.js";

interface ThinkingMessageProps {
  content: string;
}

export const ThinkingMessage = memo(function ThinkingMessage({ content }: ThinkingMessageProps) {
  const { width: terminalWidth } = useDimensions();
  const contentWidth = Math.max(0, terminalWidth - 4);

  return (
    <Box flexDirection="column" width={terminalWidth} overflow="hidden">
      <Text>
        <Text color={brand.primary}>✻ </Text>
        <Text color={brand.primary}>Thinking…</Text>
      </Text>
      {content && (
        <Box marginLeft={2} width={contentWidth} overflow="hidden">
          <Text color={colors.text.secondary} wrap="wrap">{content}</Text>
        </Box>
      )}
    </Box>
  );
});
