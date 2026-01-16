import { useMemo } from "react";
import { Box, Text } from "ink";
import { truncateText } from "../../lib/utils.js";
import { colors } from "./colors.js";

interface ExpandableTextProps {
  text: string;
  width: number;
  expanded: boolean;
  scrollOffset?: number;
  visibleLines?: number;
  isFocused?: boolean;
  color?: string;
  boldFirstLine?: boolean;
}

function wrapText(text: string, width: number): string[] {
  if (width <= 0) return [text];
  const words = text.split(" ");
  const lines: string[] = [];
  let line = "";

  for (const word of words) {
    if (!line) {
      line = word;
    } else if (line.length + 1 + word.length <= width) {
      line += " " + word;
    } else {
      lines.push(line);
      line = word;
    }
  }
  if (line) lines.push(line);
  return lines;
}

export function ExpandableText({
  text,
  width,
  expanded,
  scrollOffset = 0,
  visibleLines = 5,
  isFocused = false,
  color,
  boldFirstLine = false,
}: ExpandableTextProps) {
  const textColor = color ?? (isFocused ? colors.text.primary : colors.text.secondary);
  const effectiveWidth = width - 2;

  const lines = useMemo(() => wrapText(text, effectiveWidth), [text, effectiveWidth]);
  const needsExpansion = lines.length > 1;

  // If text fits on one line, just show it
  if (!needsExpansion) {
    return (
      <Box width={width} height={1}>
        <Text color={textColor} bold={boldFirstLine}>
          {text}
        </Text>
      </Box>
    );
  }

  // Text needs multiple lines - show collapsed or expanded
  if (!expanded) {
    const truncated = truncateText(text, effectiveWidth);
    return (
      <Box width={width} height={1}>
        <Text color={textColor} bold={boldFirstLine}>
          {truncated}
        </Text>
        {isFocused && <Text color={colors.text.muted}> ↵</Text>}
      </Box>
    );
  }

  // Expanded view with scrolling
  const needsScroll = lines.length > visibleLines;
  const actualVisibleLines = needsScroll ? visibleLines - 1 : visibleLines; // Reserve 1 line for indicator
  const maxScroll = Math.max(0, lines.length - actualVisibleLines);
  const safeOffset = Math.min(scrollOffset, maxScroll);
  const displayLines = lines.slice(safeOffset, safeOffset + actualVisibleLines);
  const canScrollUp = safeOffset > 0;
  const canScrollDown = safeOffset < maxScroll;

  return (
    <Box flexDirection="column" width={width} height={visibleLines}>
      {displayLines.map((line, i) => (
        <Text key={i} color={textColor} bold={boldFirstLine && safeOffset === 0 && i === 0}>
          {line}
        </Text>
      ))}
      {needsScroll && (
        <Text color={colors.text.muted}>
          {canScrollUp ? "▲" : " "} {safeOffset + 1}-{safeOffset + displayLines.length}/{lines.length} {canScrollDown ? "▼" : " "}
        </Text>
      )}
    </Box>
  );
}

// Helper to get max scroll offset for text
export function getTextMaxScroll(text: string, width: number, visibleLines: number): number {
  const lines = wrapText(text, width - 2);
  const needsScroll = lines.length > visibleLines;
  const actualVisibleLines = needsScroll ? visibleLines - 1 : visibleLines;
  return Math.max(0, lines.length - actualVisibleLines);
}
