import React, { memo } from "react";
import { Box, Text } from "ink";
import { Markdown } from "../../Markdown.js";
import { brand } from "../../ui/colors.js";
import { useDimensions } from "../../../contexts/index.js";
import { BULLET } from "../../../lib/constants.js";

interface AssistantMessageProps {
  content: string;
  renderMarkdown?: boolean;
}

export const AssistantMessage = memo(function AssistantMessage({
  content,
  renderMarkdown = true,
}: AssistantMessageProps) {
  const { width: terminalWidth } = useDimensions();
  const contentWidth = Math.max(0, terminalWidth - 4);

  return (
    <Box flexDirection="row" width={terminalWidth} overflow="hidden">
      <Box width={2} flexShrink={0}>
        <Text color={brand.primary}>{BULLET} </Text>
      </Box>
      <Box width={contentWidth} flexGrow={1} flexDirection="column" overflow="hidden">
        {renderMarkdown ? (
          <Markdown>{content}</Markdown>
        ) : (
          <Text wrap="wrap">{content}</Text>
        )}
      </Box>
    </Box>
  );
});
