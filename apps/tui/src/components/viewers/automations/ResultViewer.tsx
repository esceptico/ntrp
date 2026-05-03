import { useEffect, useRef } from "react";
import type { ScrollBoxRenderable } from "@opentui/core";
import type { Automation } from "../../../api/client.js";
import { colors } from "../../ui/index.js";
import { formatRelativeTime, triggersLabel } from "../../../lib/format.js";

interface ResultViewerProps {
  automation: Automation;
  scroll: number;
  setScroll: React.Dispatch<React.SetStateAction<number>>;
  width: number;
  height: number;
}

export function ResultViewer({ automation, scroll, setScroll, width, height }: ResultViewerProps) {
  const scrollRef = useRef<ScrollBoxRenderable | null>(null);
  const s = automation;
  const enabled = s.enabled;
  const isRunning = !!s.running_since;
  const statusIcon = isRunning ? "\u25B6" : enabled ? "\u2713" : "\u23F8";
  const statusLabel = isRunning ? "running" : enabled ? "enabled" : "disabled";
  const nextRun = enabled ? formatRelativeTime(s.next_run_at) : "disabled";
  const lastRun = formatRelativeTime(s.last_run_at);

  useEffect(() => {
    const box = scrollRef.current;
    if (!box) return;
    box.scrollTo(Math.max(0, scroll));
  }, [scroll]);

  useEffect(() => {
    if (scroll < 0) setScroll(0);
  }, [scroll, setScroll]);

  return (
    <scrollbox
      ref={(r: ScrollBoxRenderable) => {
        scrollRef.current = r;
      }}
      width={width}
      height={height}
      style={{ scrollbarOptions: { visible: false } }}
    >
      <box flexDirection="column" width={width}>
        {s.name && (
          <text wrapMode="word">
            <strong><span fg={colors.text.primary}>{s.name}</span></strong>
          </text>
        )}
        <text wrapMode="word"><span fg={colors.text.secondary}>{s.description}</span></text>

        <box marginTop={1} flexDirection="column">
          <text wrapMode="word">
            <span fg={colors.text.muted}>
              {statusIcon} {statusLabel}  {triggersLabel(s.triggers)}{s.writable ? "  \u270E" : ""}
            </span>
          </text>
          <text wrapMode="word">
            <span fg={colors.text.muted}>next {nextRun}  last {lastRun}</span>
          </text>
        </box>

        <box marginTop={1} flexDirection="column">
          <text><strong><span fg={colors.text.primary}>LAST RESULT</span></strong></text>
          {s.last_result ? (
            s.last_result.split("\n").map((line, idx) => (
              <text key={idx} wrapMode="word">
                <span fg={colors.text.secondary}>{line || " "}</span>
              </text>
            ))
          ) : (
            <text><span fg={colors.text.disabled}>No result yet</span></text>
          )}
        </box>
      </box>
    </scrollbox>
  );
}
