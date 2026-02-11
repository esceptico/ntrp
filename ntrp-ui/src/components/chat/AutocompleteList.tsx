import React from "react";
import { Box, Text } from "ink";
import type { SlashCommand } from "../../types.js";

interface AutocompleteListProps {
  commands: readonly SlashCommand[];
  selectedIndex: number;
  accentValue: string;
  maxDescWidth?: number;
}

export function AutocompleteList({ commands, selectedIndex, accentValue, maxDescWidth }: AutocompleteListProps) {
  const nameCol = Math.max(...commands.map((c) => c.name.length)) + 4;

  return (
    <Box flexDirection="column">
      {commands.map((cmd, i) => {
        let desc = cmd.description;
        if (maxDescWidth && desc.length > maxDescWidth) {
          desc = desc.slice(0, maxDescWidth - 3) + "...";
        }

        return (
          <Box key={cmd.name} gap={2}>
            <Box width={nameCol} flexShrink={0}>
              <Text color={i === selectedIndex ? accentValue : undefined} bold={i === selectedIndex}>
                /{cmd.name}
              </Text>
            </Box>
            <Text dimColor>{desc}</Text>
          </Box>
        );
      })}
    </Box>
  );
}
