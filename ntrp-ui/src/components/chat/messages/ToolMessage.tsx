import { memo } from "react";
import { colors } from "../../ui/colors.js";
import { useDimensions } from "../../../contexts/index.js";
import { truncateText } from "../../ui/index.js";
import { MAX_TOOL_OUTPUT_LINES, MIN_DELEGATE_DURATION_SHOW } from "../../../lib/constants.js";

const TOOL_MARKER = "\u2192"; // →

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
  const parts: string[] = [];
  if (toolCount && toolCount > 0) parts.push(`${toolCount} tool${toolCount !== 1 ? "s" : ""}`);
  if (duration && duration >= MIN_DELEGATE_DURATION_SHOW) parts.push(`${duration}s`);
  const stats = parts.length > 0 ? ` \u00B7 ${parts.join(" \u00B7 ")}` : "";
  const descText = description || "delegate";
  const contentWidth = Math.max(0, terminalWidth - 7);
  const descWidth = Math.max(0, contentWidth - 2 - stats.length);

  return (
    <box flexDirection="column" overflow="hidden" paddingLeft={3}>
      <text>
        <span fg={colors.text.disabled}>{TOOL_MARKER} </span>
        <span fg={colors.text.muted}>{truncateText(descText, descWidth)}</span>
        {stats && <span fg={colors.text.disabled}>{stats}</span>}
      </text>
      <text><span fg={colors.text.disabled}>{"  "} Done</span></text>
    </box>
  );
});

interface ToolMessageProps {
  name: string;
  content: string;
  description?: string;
  toolCount?: number;
  duration?: number;
  autoApproved?: boolean;
}

const AUTO_SUFFIX = " \u00B7 auto"; // " · auto"

export const ToolMessage = memo(function ToolMessage({
  name,
  content,
  description,
  toolCount,
  duration,
  autoApproved,
}: ToolMessageProps) {
  const { width } = useDimensions();
  const contentWidth = Math.max(0, width - 3);
  const suffix = autoApproved ? AUTO_SUFFIX : "";

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
      <box flexDirection="column" overflow="hidden" paddingLeft={3}>
        <text>
          <span fg={colors.text.disabled}>{TOOL_MARKER} </span>
          <span fg={colors.text.muted}>{truncateText(displayName, contentWidth - 2 - suffix.length)}</span>
          {suffix && <span fg={colors.text.disabled}>{suffix}</span>}
        </text>
        <text>
          <span fg={colors.text.disabled}>
            {"  "} Read <strong>{String(totalLines)}</strong> lines
          </span>
        </text>
      </box>
    );
  }

  const lines = displayContent.split("\n").filter(l => l.trim() !== "");
  const visibleLines = lines.slice(0, MAX_TOOL_OUTPUT_LINES);
  const hiddenCount = totalLines !== null
    ? Math.max(0, totalLines - MAX_TOOL_OUTPUT_LINES)
    : Math.max(0, lines.length - MAX_TOOL_OUTPUT_LINES);

  return (
    <box flexDirection="column" overflow="hidden" paddingLeft={3}>
      <text>
        <span fg={colors.text.disabled}>{TOOL_MARKER} </span>
        <span fg={colors.text.muted}>{truncateText(displayName, contentWidth - 2 - suffix.length)}</span>
        {suffix && <span fg={colors.text.disabled}>{suffix}</span>}
      </text>
      {(visibleLines.length > 0 || hiddenCount > 0) && (
        <box flexDirection="row">
          <box width={2} flexShrink={0}>
            <text><span fg={colors.text.disabled}>{"  "}</span></text>
          </box>
          <box flexDirection="column" flexGrow={1} overflow="hidden">
            {visibleLines.map((line, i) => (
              <text key={i}><span fg={colors.text.disabled}>{truncateText(line, contentWidth - 2)}</span></text>
            ))}
            {hiddenCount > 0 && (
              <text><span fg={colors.text.disabled}>{"\u2026"} +{hiddenCount} lines</span></text>
            )}
          </box>
        </box>
      )}
    </box>
  );
});
