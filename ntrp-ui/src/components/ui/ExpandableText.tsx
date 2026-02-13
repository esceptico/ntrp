import { useMemo } from "react";
import { truncateText, wrapText } from "../../lib/utils.js";
import { colors } from "./colors.js";

interface ExpandableTextProps {
  text: string;
  width: number;
  expanded: boolean;
  scrollOffset?: number;
  visibleLines?: number;
  isFocused?: boolean;
  color?: string;
}

export function ExpandableText({
  text,
  width,
  expanded,
  scrollOffset = 0,
  visibleLines = 5,
  isFocused = false,
  color,
}: ExpandableTextProps) {
  const textColor = color ?? (isFocused ? colors.text.primary : colors.text.secondary);
  const effectiveWidth = width - 2;

  const lines = useMemo(() => wrapText(text, effectiveWidth), [text, effectiveWidth]);

  // Single line — just render it
  if (lines.length <= 1) {
    return (
      <box width={width} height={1}>
        <text><span fg={textColor}>{text}</span></text>
      </box>
    );
  }

  // Fits within visibleLines — show all lines, no expand needed
  if (lines.length <= visibleLines) {
    return (
      <box flexDirection="column" width={width} height={lines.length}>
        {lines.map((line, i) => (
          <text key={i}><span fg={textColor}>{line}</span></text>
        ))}
      </box>
    );
  }

  // Exceeds visibleLines — collapsed by default, expandable
  if (!expanded) {
    const truncated = truncateText(text, effectiveWidth);
    return (
      <box width={width} height={1}>
        <text>
          <span fg={textColor}>{truncated}</span>
          {isFocused && <span fg={colors.text.muted}> {"\u21B5"}</span>}
        </text>
      </box>
    );
  }

  // Expanded with scroll
  const needsScroll = lines.length > visibleLines;
  const actualVisibleLines = needsScroll ? visibleLines - 1 : visibleLines;
  const maxScroll = Math.max(0, lines.length - actualVisibleLines);
  const safeOffset = Math.min(scrollOffset, maxScroll);
  const displayLines = lines.slice(safeOffset, safeOffset + actualVisibleLines);
  const canScrollUp = safeOffset > 0;
  const canScrollDown = safeOffset < maxScroll;

  return (
    <box flexDirection="column" width={width} height={visibleLines}>
      {displayLines.map((line, i) => (
        <text key={i}><span fg={textColor}>{line}</span></text>
      ))}
      {needsScroll && (
        <text>
          <span fg={colors.text.muted}>
            {canScrollUp ? "\u25B2" : " "} {safeOffset + 1}-{safeOffset + displayLines.length}/{lines.length} {canScrollDown ? "\u25BC" : " "}
          </span>
        </text>
      )}
    </box>
  );
}

export function getTextMaxScroll(text: string, width: number, visibleLines: number): number {
  const lines = wrapText(text, width - 2);
  const needsScroll = lines.length > visibleLines;
  const actualVisibleLines = needsScroll ? visibleLines - 1 : visibleLines;
  return Math.max(0, lines.length - actualVisibleLines);
}
