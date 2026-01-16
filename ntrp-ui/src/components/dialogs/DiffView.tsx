import React, { useMemo } from "react";
import { Box, Text } from "ink";
import { colors } from "../ui/colors.js";
import { truncateText } from "../ui/index.js";
import { MAX_DIFF_LINES } from "../../lib/constants.js";

interface DiffLine {
  type: "added" | "removed" | "context";
  content: string;
}

function parseDiff(diff: string): { lines: DiffLine[]; added: number; removed: number } {
  const rawLines = diff.split("\n");
  const result: DiffLine[] = [];
  let added = 0, removed = 0;

  for (const line of rawLines) {
    if (line.startsWith("---") || line.startsWith("+++") || line.startsWith("@@")) continue;
    if (line.startsWith("+")) { result.push({ type: "added", content: line.slice(1) }); added++; }
    else if (line.startsWith("-")) { result.push({ type: "removed", content: line.slice(1) }); removed++; }
    else if (line.length > 0) { result.push({ type: "context", content: line.startsWith(" ") ? line.slice(1) : line }); }
  }

  return { lines: result, added, removed };
}

interface DiffViewProps {
  diff: string;
  width: number;
}

export function DiffView({ diff, width }: DiffViewProps) {
  const { lines, added, removed } = useMemo(() => parseDiff(diff), [diff]);
  const displayLines = lines.length > MAX_DIFF_LINES
    ? [...lines.slice(0, MAX_DIFF_LINES - 2), ...lines.slice(-2)]
    : lines;
  const skipped = lines.length > MAX_DIFF_LINES ? lines.length - MAX_DIFF_LINES : 0;
  const lineWidth = Math.max(0, width - 2);

  return (
    <Box flexDirection="column" width={width} overflow="hidden">
      <Text>
        <Text color={colors.diff.added}>+{added}</Text>
        <Text color={colors.text.disabled}>/</Text>
        <Text color={colors.diff.removed}>-{removed}</Text>
        <Text color={colors.text.disabled}> lines</Text>
      </Text>
      {displayLines.map((line, i) => (
        <Text key={i} color={line.type === "added" ? colors.diff.added : line.type === "removed" ? colors.diff.removed : colors.text.disabled}>
          {line.type === "added" ? "+" : line.type === "removed" ? "-" : " "} {truncateText(line.content, lineWidth)}
        </Text>
      ))}
      {skipped > 0 && <Text color={colors.text.disabled}>  ⋯ {skipped} more</Text>}
    </Box>
  );
}
