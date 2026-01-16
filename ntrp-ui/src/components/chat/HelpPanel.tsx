import React from "react";
import { Box, Text } from "ink";

interface HelpPanelProps {
  accentValue: string;
}

export function HelpPanel({ accentValue }: HelpPanelProps) {
  return (
    <Box flexDirection="column" paddingLeft={2}>
      <Box gap={4}>
        <Box flexDirection="column">
          <Text><Text color={accentValue}>/</Text> for commands</Text>
          <Text><Text color={accentValue}>\⏎</Text> or <Text color={accentValue}>shift+⏎</Text> newline</Text>
        </Box>
        <Box flexDirection="column">
          <Text dimColor>ctrl+k  kill to end</Text>
          <Text dimColor>ctrl+u  kill to start</Text>
          <Text dimColor>ctrl+w  kill word ←</Text>
        </Box>
        <Box flexDirection="column">
          <Text dimColor>ctrl+a  home</Text>
          <Text dimColor>ctrl+e  end</Text>
          <Text dimColor>esc     clear input</Text>
        </Box>
        <Box flexDirection="column">
          <Text dimColor>↑/↓      navigate autocomplete</Text>
          <Text dimColor>tab      confirm selection</Text>
          <Text dimColor>ctrl+←→  word jump</Text>
        </Box>
      </Box>
    </Box>
  );
}
