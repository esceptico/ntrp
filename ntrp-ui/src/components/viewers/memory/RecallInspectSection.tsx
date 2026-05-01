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
  if (!text) return ["No memory matches"];
  return text.split("\n").flatMap((line) => (line ? wrapText(line, width) : [""]));
}

function sourceLines(tab: RecallInspectTabState, width: number): string[] {
  const result = tab.result;
  if (!result) return [];

  const lines: string[] = [];
  if (result.observations.length > 0) {
    lines.push("", "SOURCES - PATTERNS");
    for (const obs of result.observations) {
      lines.push(`${obs.evidence_count} facts · ${truncateText(obs.summary, Math.max(10, width - 12))}`);
    }
  }
  if (result.facts.length > 0) {
    lines.push("", "SOURCES - FACTS");
    for (const fact of result.facts) {
      const label = `${fact.kind} · ${fact.lifetime}`;
      lines.push(`${label} · ${truncateText(fact.text, Math.max(10, width - label.length - 3))}`);
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
        ...wrappedLines(result.formatted_recall, contentWidth),
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
          placeholder="memory query"
          textColor={colors.text.primary}
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
            <span fg={colors.text.muted}>{result.observations.length} patterns</span>
            <span fg={colors.text.disabled}> | </span>
            <span fg={colors.text.muted}>{result.facts.length} facts</span>
            <span fg={colors.text.disabled}> | session </span>
            <span fg={colors.text.muted}>{result.session.profile_facts.length} profile</span>
            <span fg={colors.text.disabled}> / </span>
            <span fg={colors.text.muted}>{result.session.observations.length} patterns</span>
          </text>
        ) : (
          <text><span fg={colors.text.disabled}>Enter a query to test retrieval</span></text>
        )}
      </box>

      <box flexDirection="column" marginTop={1} height={outputHeight} overflow="hidden">
        {visible.map((line, index) => {
          const isHeading = line.startsWith("**") || line.startsWith("SOURCES");
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
