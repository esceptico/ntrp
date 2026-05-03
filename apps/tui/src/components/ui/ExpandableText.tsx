import { useEffect, useMemo, useRef } from "react";
import type { ScrollBoxRenderable } from "@opentui/core";
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
  const scrollRef = useRef<ScrollBoxRenderable | null>(null);
  const textColor = color ?? (isFocused ? colors.text.primary : colors.text.secondary);
  const effectiveWidth = width - 2;
  const lines = useMemo(() => wrapText(text, effectiveWidth), [text, effectiveWidth]);
  const truncated = truncateText(text, effectiveWidth);

  useEffect(() => {
    if (!expanded || !scrollRef.current) return;
    scrollRef.current.scrollTo(Math.max(0, scrollOffset));
  }, [expanded, scrollOffset]);

  if (!expanded) {
    if (lines.length <= visibleLines) {
      return (
        <box flexDirection="column" width={width} height={Math.max(1, lines.length)}>
          {lines.map((line, i) => (
            <text key={i}><span fg={textColor}>{line || " "}</span></text>
          ))}
        </box>
      );
    }
    return (
      <box width={width} height={1}>
        <text>
          <span fg={textColor}>{truncated}</span>
          {isFocused && <span fg={colors.text.muted}> {"\u21B5"}</span>}
        </text>
      </box>
    );
  }

  return (
    <scrollbox
      ref={(r: ScrollBoxRenderable) => { scrollRef.current = r; }}
      width={width}
      height={visibleLines}
      style={{ scrollbarOptions: { visible: false } }}
    >
      <text wrapMode="word"><span fg={textColor}>{text || " "}</span></text>
    </scrollbox>
  );
}

export function getTextMaxScroll(text: string, width: number, visibleLines: number): number {
  const lines = wrapText(text, Math.max(1, width - 2));
  return Math.max(0, lines.length - Math.max(1, visibleLines));
}
