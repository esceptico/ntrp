import React from "react";
import { Box, Text } from "ink";
import type { SlashCommand } from "../../types.js";

interface AutocompleteListProps {
  commands: readonly SlashCommand[];
  selectedIndex: number;
  accentValue: string;
}

export function AutocompleteList({ commands, selectedIndex, accentValue }: AutocompleteListProps) {
  return (
    <Box flexDirection="row" flexWrap="wrap" gap={1}>
      {commands.map((cmd, i) => (
        <Text key={cmd.name} color={i === selectedIndex ? accentValue : undefined} bold={i === selectedIndex}>
          /{cmd.name}
        </Text>
      ))}
    </Box>
  );
}
