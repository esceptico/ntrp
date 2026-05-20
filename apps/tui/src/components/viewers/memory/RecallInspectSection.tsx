import type { RecallInspectTabState } from "../../../hooks/useRecallInspectTab.js";
import { colors, TextInputField } from "../../ui/index.js";
import { truncateText, wrapText } from "../../../lib/utils.js";

interface RecallInspectSectionProps {
  tab: RecallInspectTabState;
  height: number;
  width: number;
}

function windowText(value: string, cursorPos: number, maxWidth: number): { text: string; cursor: number } {
  if (maxWidth <= 0) return { text: "", cursor: 0 };
  if (value.length <= maxWidth) return { text: value, cursor: cursorPos };
  const start = Math.min(Math.max(0, cursorPos - Math.floor(maxWidth / 2)), value.length - maxWidth);
  return { text: value.slice(start, start + maxWidth), cursor: cursorPos - start };
}

function wrappedLines(text: string | null, width: number): string[] {
  if (!text) return ["No knowledge matches"];
  return text.split("\n").flatMap((line) => (line ? wrapText(line, width) : [""]));
}

function sourceLines(tab: RecallInspectTabState, width: number): string[] {
  const result = tab.result;
  if (!result) return [];

  const lines: string[] = [];
  if (result.candidates.length > 0) {
    lines.push("", "ACTIVATED");
    for (const item of result.candidates) {
      const label = `${item.object_type} · ${item.activation} · ${item.score.toFixed(2)}`;
      lines.push(`${label} · ${truncateText(item.title, Math.max(10, width - label.length - 3))}`);
      if (item.reasons.length > 0) {
        lines.push(`why: ${truncateText(item.reasons.join(", "), Math.max(10, width - 5))}`);
      }
    }
  }
  return lines;
}

export function RecallInspectSection({ tab, height, width }: RecallInspectSectionProps) {
  const contentWidth = Math.max(20, width - 4);
  const inputWidth = Math.max(10, contentWidth - 8);
  const queryWindow = windowText(tab.query, tab.cursorPos, inputWidth);
  const result = tab.result;
  const outputHeight = Math.max(3, height - 7);
  const lines = result
    ? [
        ...wrappedLines(result.prompt_context, contentWidth),
        ...sourceLines(tab, contentWidth),
      ]
    : [];
  const maxOffset = Math.max(0, lines.length - outputHeight);
  const offset = Math.min(tab.scrollOffset, maxOffset);
  const visible = lines.slice(offset, offset + outputHeight);

  return (
    <box flexDirection="column" width={width} height={height} paddingLeft={1} paddingRight={1} overflow="hidden">
      <box flexDirection="row">
        <text><span fg={colors.text.muted}>SEARCH</span><span fg={colors.text.disabled}> </span></text>
        <TextInputField
          value={queryWindow.text}
          cursorPos={queryWindow.cursor}
          placeholder={tab.inputActive ? "memory query" : "press enter to edit query"}
          showCursor={tab.inputActive}
          textColor={tab.inputActive ? colors.text.primary : colors.text.secondary}
        />
      </box>

      <box marginTop={1}>
        {tab.loading ? (
          <text><span fg={colors.tool.running}>Inspecting...</span></text>
        ) : tab.error ? (
          <text><span fg={colors.status.error}>{truncateText(tab.error, contentWidth)}</span></text>
        ) : result ? (
          <text>
            <span fg={colors.text.secondary}>search result</span>
            <span fg={colors.text.disabled}> | </span>
            <span fg={colors.text.muted}>{result.candidates.length} activated</span>
            <span fg={colors.text.disabled}> | </span>
            <span fg={colors.text.muted}>{result.omitted.length} omitted</span>
          </text>
        ) : (
          <text><span fg={colors.text.disabled}>Enter a query to preview activation</span></text>
        )}
      </box>

      <box flexDirection="column" marginTop={1} height={outputHeight} overflow="hidden">
        {visible.map((line, index) => {
          const isHeading = line.startsWith("**") || line.startsWith("SOURCES") || line === "ACTIVATED";
          return (
            <text key={`${offset}-${index}`}>
              <span fg={isHeading ? colors.text.secondary : colors.text.muted}>{line || " "}</span>
            </text>
          );
        })}
      </box>
    </box>
  );
}
