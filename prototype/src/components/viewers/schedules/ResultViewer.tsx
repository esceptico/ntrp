import { useEffect } from "react";
import type { Schedule } from "../../../api/client.js";
import { colors } from "../../ui/index.js";
import { wrapText } from "../../../lib/utils.js";
import { formatRelativeTime } from "../../../lib/format.js";

interface ResultViewerProps {
  schedule: Schedule;
  scroll: number;
  setScroll: React.Dispatch<React.SetStateAction<number>>;
  width: number;
  height: number;
}

export function ResultViewer({ schedule, scroll, setScroll, width, height }: ResultViewerProps) {
  const s = schedule;
  const enabled = s.enabled;
  const isRunning = !!s.running_since;
  const statusIcon = isRunning ? "\u25B6" : enabled ? "\u2713" : "\u23F8";
  const statusLabel = isRunning ? "running" : enabled ? "enabled" : "disabled";
  const nextRun = enabled ? formatRelativeTime(s.next_run_at) : "disabled";
  const lastRun = formatRelativeTime(s.last_run_at);

  const descLines = wrapText(s.description, width);
  // Header: name(1) + desc(N) + blank(1) + meta(2) + blank(1) + label(1) = N+6
  const headerLines = (s.name ? 1 : 0) + descLines.length + 1 + 2 + 1 + 1;
  const resultVisibleLines = Math.max(1, height - headerLines - 1);

  // Wrap each raw line to fit width, then flatten into a single line array
  const rawLines = s.last_result ? s.last_result.split("\n") : [];
  const resultLines = rawLines.flatMap((line) =>
    line.length > width ? wrapText(line, width) : [line]
  );
  const maxScroll = Math.max(0, resultLines.length - resultVisibleLines);

  useEffect(() => {
    if (scroll > maxScroll) setScroll(maxScroll);
  }, [scroll, maxScroll, setScroll]);

  const clampedScroll = Math.min(scroll, maxScroll);
  const visible = resultLines.slice(clampedScroll, clampedScroll + resultVisibleLines);

  return (
    <box flexDirection="column" width={width} height={height} overflow="hidden">
      {s.name && (
        <text><strong><span fg={colors.text.primary}>{s.name}</span></strong></text>
      )}
      {descLines.map((line, i) => (
        <text key={i}><span fg={colors.text.secondary}>{line}</span></text>
      ))}

      <box marginTop={1} flexDirection="column">
        <text>
          <span fg={colors.text.muted}>{statusIcon} {statusLabel}</span>
          <span fg={colors.text.muted}>  {s.time_of_day}  {s.recurrence}</span>
          {s.writable && <span fg={colors.text.muted}>  {"\u270E"}</span>}
        </text>
        <text>
          <span fg={colors.text.muted}>next {nextRun}  last {lastRun}</span>
        </text>
      </box>

      <box marginTop={1} flexDirection="column" flexGrow={1} overflow="hidden">
        {resultLines.length > 0 ? (
          <>
            <text><span fg={colors.text.primary}><strong>LAST RESULT</strong></span></text>
            {visible.map((line, i) => (
              <text key={i}><span fg={colors.text.secondary}>{line}</span></text>
            ))}
            {resultLines.length > resultVisibleLines && (
              <text>
                <span fg={colors.text.disabled}>
                  {clampedScroll + 1}-{Math.min(clampedScroll + resultVisibleLines, resultLines.length)} of {resultLines.length}
                </span>
              </text>
            )}
          </>
        ) : (
          <text><span fg={colors.text.disabled}>No result yet</span></text>
        )}
      </box>
    </box>
  );
}
