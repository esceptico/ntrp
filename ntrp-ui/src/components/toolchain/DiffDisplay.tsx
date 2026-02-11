import React, { useMemo } from "react";
import { Box, Text } from "ink";
import { truncateText } from "../../lib/utils.js";
import { colors } from "../ui/index.js";

interface StructuredDiffDisplayProps {
  before: string;
  after: string;
  path: string;
  prefix: string;
  width: number;
  maxLines?: number;
}

function computeUnifiedDiff(before: string, after: string): string[] {
  const oldLines = before.split('\n');
  const newLines = after.split('\n');
  const result: string[] = [];

  // Simple line-by-line diff: find changed regions
  let i = 0;
  let j = 0;
  while (i < oldLines.length || j < newLines.length) {
    if (i < oldLines.length && j < newLines.length && oldLines[i] === newLines[j]) {
      i++;
      j++;
      continue;
    }
    // Find the extent of the change
    // Look ahead for next matching line
    let matchI = -1;
    let matchJ = -1;
    const searchLimit = Math.max(oldLines.length - i, newLines.length - j);
    for (let d = 1; d <= searchLimit; d++) {
      for (let oi = 0; oi <= d && i + oi < oldLines.length; oi++) {
        const ni = d - oi;
        if (j + ni < newLines.length && i + oi < oldLines.length && oldLines[i + oi] === newLines[j + ni]) {
          matchI = i + oi;
          matchJ = j + ni;
          break;
        }
      }
      if (matchI >= 0) break;
    }
    if (matchI < 0) { matchI = oldLines.length; matchJ = newLines.length; }

    // Emit context line before change
    const ctxStart = Math.max(0, i - 1);
    if (ctxStart < i && result.length === 0) {
      result.push(` ${oldLines[ctxStart]}`);
    }

    // Emit removed lines
    for (let k = i; k < matchI; k++) {
      result.push(`-${oldLines[k]}`);
    }
    // Emit added lines
    for (let k = j; k < matchJ; k++) {
      result.push(`+${newLines[k]}`);
    }

    i = matchI;
    j = matchJ;
  }

  return result;
}

export function StructuredDiffDisplay({ before, after, path, prefix, width, maxLines = 10 }: StructuredDiffDisplayProps) {
  const { diffLines, added, removed } = useMemo(() => {
    const lines = computeUnifiedDiff(before, after);
    return {
      diffLines: lines,
      added: lines.filter(l => l.startsWith('+')).length,
      removed: lines.filter(l => l.startsWith('-')).length,
    };
  }, [before, after]);

  const lines = diffLines.slice(0, maxLines);
  const totalLines = diffLines.length;
  const lineWidth = Math.max(0, width - prefix.length - 2);

  return (
    <Box flexDirection="column" marginLeft={2} width={width} overflow="hidden">
      <Text dimColor>{prefix}{path}</Text>
      {lines.map((line, i) => (
        <Text
          key={i}
          color={
            line.startsWith('+') ? colors.diff.added :
            line.startsWith('-') ? colors.diff.removed :
            undefined
          }
        >
          {prefix}{truncateText(line, lineWidth)}
        </Text>
      ))}
      {totalLines > maxLines && (
        <Text dimColor>{prefix}  ... {totalLines - maxLines} more lines</Text>
      )}
      <Text dimColor>{prefix}  <Text color={colors.diff.added}>+{added}</Text> <Text color={colors.diff.removed}>-{removed}</Text></Text>
    </Box>
  );
}
