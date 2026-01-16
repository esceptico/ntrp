import React, { memo } from "react";
import { Box, Text } from "ink";
import { colors } from "../../ui/colors.js";
import { useDimensions } from "../../../contexts/index.js";
import { truncateText } from "../../ui/index.js";

interface UserMessageProps {
  content: string;
}

export const UserMessage = memo(function UserMessage({ content }: UserMessageProps) {
  const { width: terminalWidth } = useDimensions();
  const contentWidth = Math.max(0, terminalWidth - 4);

  return (
    <Box width={terminalWidth} overflow="hidden">
      <Text>
        <Text color={colors.status.warning} bold>{">"} </Text>
        <Text>{truncateText(content, contentWidth)}</Text>
      </Text>
    </Box>
  );
});
