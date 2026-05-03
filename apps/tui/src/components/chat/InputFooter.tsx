import { useState, useEffect, useCallback, useMemo } from "react";
import { colors } from "../ui/colors.js";
import { truncateText } from "../../lib/utils.js";
import { useKeypress, type Key } from "../../hooks/index.js";
import type { BackgroundTask } from "../../stores/streamingStore.js";
import { BrailleSort } from "../ui/spinners/index.js";
import { TRANSCRIPT_GUTTER_WIDTH } from "./messages/TranscriptRow.js";

function formatElapsed(ms: number): string {
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  return `${m}m${s % 60}s`;
}

function TaskDetails({ tasks, onCancel }: { tasks: Map<string, BackgroundTask>; onCancel?: (id: string) => void }) {
  const [, tick] = useState(0);

  useEffect(() => {
    if (tasks.size === 0) return;
    const id = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, [tasks.size]);

  const entries = useMemo(() => [...tasks.values()].sort((a, b) => a.startedAt - b.startedAt), [tasks]);
  const now = Date.now();

  return (
    <box flexDirection="column" marginLeft={TRANSCRIPT_GUTTER_WIDTH} marginBottom={1}>
      {entries.map((t) => {
        const last = t.activity.length > 0 ? t.activity[t.activity.length - 1] : null;
        return (
          <box key={t.id} flexDirection="column">
            <box flexDirection="row">
              <text>
                <span fg={colors.status.processing}>◦ </span>
                <span fg={colors.text.muted}>{truncateText(t.command, 50)}</span>
                <span fg={colors.text.disabled}> · {t.id} · {formatElapsed(now - t.startedAt)}</span>
                <span fg={colors.text.disabled}> · {t.activity.length} calls</span>
              </text>
              {onCancel && (
                <box marginLeft={1} onMouseDown={() => onCancel(t.id)}>
                  <text><span fg={colors.status.error}> ✕</span></text>
                </box>
              )}
            </box>
            {last && (
              <text>
                <span fg={colors.text.disabled}>  ⎿ {truncateText(last, 58)}</span>
              </text>
            )}
          </box>
        );
      })}
    </box>
  );
}

export interface InputFooterProps {
  accentValue: string;
  escHint: boolean;
  copiedFlash: boolean;
  backgroundTaskCount?: number;
  backgroundTasks?: Map<string, BackgroundTask>;
  onCancelBackgroundTask?: (taskId: string) => void;
  indexStatus?: {
    indexing: boolean;
    progress: { total: number; done: number };
    reembedding?: boolean;
    reembed_progress?: { total: number; done: number } | null;
  } | null;
}

export function InputFooter({ accentValue, escHint, copiedFlash, backgroundTaskCount, backgroundTasks, onCancelBackgroundTask, indexStatus }: InputFooterProps) {
  const [expanded, setExpanded] = useState(false);
  const hasTasks = backgroundTaskCount != null && backgroundTaskCount > 0;

  useKeypress(
    useCallback((key: Key) => {
      if (key.ctrl && key.name === "b") setExpanded((v) => !v);
      if (key.ctrl && key.name === "x" && expanded && onCancelBackgroundTask && backgroundTasks?.size) {
        const latest = [...backgroundTasks.values()].sort((a, b) => b.startedAt - a.startedAt)[0];
        if (latest) onCancelBackgroundTask(latest.id);
      }
    }, [expanded, onCancelBackgroundTask, backgroundTasks]),
    { isActive: hasTasks }
  );
  const hasTaskDetails = backgroundTasks && backgroundTasks.size > 0;
  const hasIndexWork = Boolean(indexStatus?.indexing || indexStatus?.reembedding);
  const hasFeedback = copiedFlash || escHint;

  if (!expanded && !hasTasks && !hasIndexWork && !hasFeedback) {
    return null;
  }

  return (
    <box flexDirection="column">
      {expanded && hasTaskDetails && <TaskDetails tasks={backgroundTasks} onCancel={onCancelBackgroundTask} />}
      <box flexDirection="row" justifyContent="space-between">
        <box flexDirection="row" marginLeft={TRANSCRIPT_GUTTER_WIDTH}>
          {hasTasks ? (
            <box onMouseDown={() => setExpanded((v) => !v)}>
              <text>
                <span fg={colors.text.disabled}>{backgroundTaskCount} {backgroundTaskCount === 1 ? "task" : "tasks"} in background </span>
                <span fg={colors.footer}>ctrl+b</span>
              </text>
            </box>
          ) : hasIndexWork ? (
            <box flexDirection="row" gap={1}>
              <BrailleSort width={8} color={accentValue} interval={40} />
              <text><span fg={colors.text.muted}>{indexStatus?.reembedding ? "re-embedding" : "indexing"}</span></text>
            </box>
          ) : null}
          <text>
            {copiedFlash ? (
              <span fg={colors.text.muted}>Copied to clipboard</span>
            ) : escHint ? (
              <span fg={accentValue}>esc again to clear</span>
            ) : null}
          </text>
        </box>
      </box>
    </box>
  );
}
