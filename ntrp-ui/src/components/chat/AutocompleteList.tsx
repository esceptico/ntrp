import React from "react";
import { Box, Text } from "ink";
import type { SlashCommand } from "../../types.js";

interface AutocompleteListProps {
  commands: SlashCommand[];
  selectedIndex: number;
  accentValue: string;
}

export function AutocompleteList({ commands, selectedIndex, accentValue }: AutocompleteListProps) {
  return (
    <Box flexDirection="column">
      {commands.map((cmd, i) => (
        <Text key={cmd.name} color={i === selectedIndex ? accentValue : undefined} bold={i === selectedIndex}>
          {"  "}/{cmd.name} <Text dimColor>{cmd.description}</Text>
        </Text>
      ))}
    </Box>
  );
}
