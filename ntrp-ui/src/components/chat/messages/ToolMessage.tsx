import { memo } from "react";
import { colors, useThemeVersion } from "../../ui/colors.js";
import { useDimensions } from "../../../contexts/index.js";
import { truncateText } from "../../ui/index.js";
import { MAX_TOOL_OUTPUT_LINES, MIN_RESEARCH_DURATION_SHOW } from "../../../lib/constants.js";

const TOOL_MARKER = "\u2192"; // →

function isReadTool(name: string): boolean {
  return ["read_file", "view"].includes(name);
}

interface ResearchMessageProps {
  description?: string;
  toolCount?: number;
  duration?: number;
  cancelled?: boolean;
}

const ResearchMessage = memo(function ResearchMessage({
  description,
  toolCount,
  duration,
  cancelled,
}: ResearchMessageProps) {
  useThemeVersion();
  const { width: terminalWidth } = useDimensions();
  const parts: string[] = [];
  if (toolCount && toolCount > 0) parts.push(`${toolCount} tool${toolCount !== 1 ? "s" : ""}`);
  if (duration && duration >= MIN_RESEARCH_DURATION_SHOW) parts.push(`${duration}s`);
  const stats = parts.length > 0 ? ` \u00B7 ${parts.join(" \u00B7 ")}` : "";
  const descText = description || "research";
  const contentWidth = Math.max(0, terminalWidth - 7);
  const descWidth = Math.max(0, contentWidth - 2 - stats.length);
  const statusLabel = cancelled ? "Cancelled" : "Done";

  return (
    <box flexDirection="column" overflow="hidden" paddingLeft={3}>
      <text>
        <span fg={cancelled ? colors.tool.error : colors.tool.completed}>{TOOL_MARKER} </span>
        <span fg={colors.text.muted}>{truncateText(descText, descWidth)}</span>
        {stats && <span fg={colors.text.disabled}>{stats}</span>}
      </text>
      <text><span fg={cancelled ? colors.status.error : colors.text.disabled}>{"  "} {statusLabel}</span></text>
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
  data?: Record<string, unknown>;
}

const AUTO_SUFFIX = " \u00B7 auto"; // " · auto"

function metadataSummary(data?: Record<string, unknown>): string | null {
  if (!data) return null;
  const keys = Object.keys(data).filter((key) => data[key] !== undefined && data[key] !== null);
  if (keys.length === 0) return null;
  const visible = keys.slice(0, 4).join(", ");
  return keys.length > 4 ? `${visible}, +${keys.length - 4}` : visible;
}

export const ToolMessage = memo(function ToolMessage({
  name,
  content,
  description,
  toolCount,
  duration,
  autoApproved,
  data,
}: ToolMessageProps) {
  useThemeVersion();
  const { width } = useDimensions();
  const contentWidth = Math.max(0, width - 3);
  const metadataWidth = Math.max(0, contentWidth - 11);
  const suffix = autoApproved ? AUTO_SUFFIX : "";

  if (name === "research") {
    return (
      <ResearchMessage
        description={description}
        toolCount={toolCount}
        duration={duration}
        cancelled={content === "Cancelled"}
      />
    );
  }

  const displayName = description || name;
  const metadata = metadataSummary(data);
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
          <span fg={colors.tool.completed}>{TOOL_MARKER} </span>
          <span fg={colors.text.muted}>{truncateText(displayName, contentWidth - 2 - suffix.length)}</span>
          {suffix && <span fg={colors.status.success}>{suffix}</span>}
        </text>
        <text>
          <span fg={colors.text.disabled}>
            {"  "} Read <strong>{String(totalLines)}</strong> lines
          </span>
        </text>
        {metadata && (
          <text><span fg={colors.text.disabled}>{"  "} metadata {truncateText(metadata, metadataWidth)}</span></text>
        )}
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
        <span fg={colors.tool.completed}>{TOOL_MARKER} </span>
        <span fg={colors.text.muted}>{truncateText(displayName, contentWidth - 2 - suffix.length)}</span>
        {suffix && <span fg={colors.status.success}>{suffix}</span>}
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
            {metadata && (
              <text><span fg={colors.text.disabled}>metadata {truncateText(metadata, metadataWidth)}</span></text>
            )}
          </box>
        </box>
      )}
      {visibleLines.length === 0 && hiddenCount === 0 && metadata && (
        <text><span fg={colors.text.disabled}>{"  "} metadata {truncateText(metadata, metadataWidth)}</span></text>
      )}
    </box>
  );
});
