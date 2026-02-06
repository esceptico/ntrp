import React from "react";
import { Box, Text } from "ink";
import { truncateText } from "../../lib/utils.js";
import { colors } from "../ui/index.js";

interface DiffDisplayProps {
  diff: string;
  prefix: string;
  width: number;
  maxLines?: number;
}

export function DiffDisplay({ diff, prefix, width, maxLines = 10 }: DiffDisplayProps) {
  const allLines = diff.split('\n');
  const lines = allLines.slice(0, maxLines);
  const totalLines = allLines.length;
  const lineWidth = Math.max(0, width - prefix.length - 2);

  return (
    <Box flexDirection="column" marginLeft={2} width={width} overflow="hidden">
      {lines.map((line, i) => (
        <Text
          key={i}
          color={
            line.startsWith('+') && !line.startsWith('+++') ? colors.diff.added :
            line.startsWith('-') && !line.startsWith('---') ? colors.diff.removed :
            line.startsWith('@') ? colors.text.muted :
            undefined
          }
          dimColor={line.startsWith('@@') || line.startsWith('---') || line.startsWith('+++')}
        >
          {prefix}{truncateText(line, lineWidth)}
        </Text>
      ))}
      {totalLines > maxLines && (
        <Text dimColor>{prefix}  ... {totalLines - maxLines} more lines</Text>
      )}
    </Box>
  );
}
