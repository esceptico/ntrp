import React, { memo } from "react";
import { Box, Text } from "ink";
import { colors } from "../../ui/colors.js";
import { useDimensions } from "../../../contexts/index.js";
import { useAccentColor } from "../../../hooks/index.js";
import { truncateText } from "../../ui/index.js";
import { BULLET, MAX_TOOL_OUTPUT_LINES, MIN_DELEGATE_DURATION_SHOW } from "../../../lib/constants.js";

function isReadTool(name: string): boolean {
  return ["read_note", "read_file", "view"].includes(name);
}

interface DelegateMessageProps {
  description?: string;
  toolCount?: number;
  duration?: number;
}

const DelegateMessage = memo(function DelegateMessage({
  description,
  toolCount,
  duration,
}: DelegateMessageProps) {
  const { width: terminalWidth } = useDimensions();
  const { accentValue } = useAccentColor();
  const parts: string[] = [];
  if (toolCount && toolCount > 0) parts.push(`${toolCount} tool${toolCount !== 1 ? "s" : ""}`);
  if (duration && duration >= MIN_DELEGATE_DURATION_SHOW) parts.push(`${duration}s`);
  const stats = parts.length > 0 ? ` · ${parts.join(" · ")}` : "";
  const descText = description || "delegate";
  const contentWidth = Math.max(0, terminalWidth - 10);

  return (
    <Box flexDirection="column" width={terminalWidth} overflow="hidden">
      <Text>
        <Text color={accentValue}>{BULLET} </Text>
        <Text>{truncateText(descText, contentWidth)}</Text>
        {stats && <Text color={colors.text.muted}>{stats}</Text>}
      </Text>
      <Text color={colors.text.muted}>⎿ Done</Text>
    </Box>
  );
});

interface ToolMessageProps {
  name: string;
  content: string;
  description?: string;
  toolCount?: number;
  duration?: number;
}

export const ToolMessage = memo(function ToolMessage({
  name,
  content,
  description,
  toolCount,
  duration,
}: ToolMessageProps) {
  const { width: terminalWidth } = useDimensions();
  const { accentValue } = useAccentColor();
  const contentWidth = Math.max(0, terminalWidth - 6);

  if (name === "delegate" || name === "explore") {
    return (
      <DelegateMessage
        description={description}
        toolCount={toolCount}
        duration={duration}
      />
    );
  }

  const displayName = description || name;
  const lineCountMatch = content.match(/^\[(\d+)\s*lines\]\n/);
  let totalLines: number | null = null;
  let displayContent = content;

  if (lineCountMatch) {
    totalLines = parseInt(lineCountMatch[1], 10);
    displayContent = content.slice(lineCountMatch[0].length);
    displayContent = displayContent.replace(/\n\n\.\.\.\s*\[truncated\]$/, "");
  }

  if (isReadTool(name) && totalLines !== null) {
    return (
      <Box flexDirection="column" width={terminalWidth} overflow="hidden">
        <Text>
          <Text color={accentValue}>{BULLET} </Text>
          <Text>{truncateText(displayName, contentWidth)}</Text>
        </Text>
        <Text color={colors.text.secondary}>
          ⎿ Read <Text bold>{totalLines}</Text> lines
        </Text>
      </Box>
    );
  }

  const lines = displayContent.split("\n").filter(l => l.trim() !== "");
  const visibleLines = lines.slice(0, MAX_TOOL_OUTPUT_LINES);
  const hiddenCount = totalLines !== null
    ? Math.max(0, totalLines - MAX_TOOL_OUTPUT_LINES)
    : Math.max(0, lines.length - MAX_TOOL_OUTPUT_LINES);

  return (
    <Box flexDirection="column" width={terminalWidth} overflow="hidden">
      <Text>
        <Text color={accentValue}>{BULLET} </Text>
        <Text>{truncateText(displayName, contentWidth)}</Text>
      </Text>
      {visibleLines.map((line, i) => (
        <Text key={i} color={colors.text.secondary}>
          {i === 0 ? "⎿ " : "  "}{truncateText(line, contentWidth - 2)}
        </Text>
      ))}
      {hiddenCount > 0 && (
        <Text color={colors.text.muted} dimColor>{"  "}… +{hiddenCount} lines</Text>
      )}
    </Box>
  );
});
