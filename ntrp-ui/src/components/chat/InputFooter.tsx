import { useState, useEffect, useCallback, useMemo } from "react";
import { Status, type Status as StatusType } from "../../lib/constants.js";
import { colors } from "../ui/colors.js";
import { truncateText } from "../../lib/utils.js";
import { useKeypress, type Key } from "../../hooks/index.js";
import type { BackgroundTask } from "../../stores/streamingStore.js";
import { BraillePendulum, BrailleCompress, BrailleSort, CyclingStatus } from "../ui/spinners/index.js";

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
    <box flexDirection="column" marginLeft={3} marginBottom={1}>
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
  isStreaming: boolean;
  status: StatusType;
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

export function InputFooter({ isStreaming, status, accentValue, escHint, copiedFlash, backgroundTaskCount, backgroundTasks, onCancelBackgroundTask, indexStatus }: InputFooterProps) {
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

  if (isStreaming || status === Status.COMPRESSING) {
    return (
      <box flexDirection="column">
        {expanded && hasTaskDetails && <TaskDetails tasks={backgroundTasks} onCancel={onCancelBackgroundTask} />}
        <box flexDirection="row" justifyContent="space-between">
          <box flexDirection="row" gap={1} flexGrow={1}>
            <box marginLeft={1}>
              {status === Status.COMPRESSING ? (
                <BrailleCompress width={8} color={accentValue} interval={30} />
              ) : (
                <BraillePendulum width={8} color={accentValue} spread={1} interval={20} />
              )}
            </box>
            {status === Status.COMPRESSING ? (
              <text><span fg={colors.text.muted}>compressing context</span></text>
            ) : (
              <CyclingStatus status={status} isStreaming={isStreaming} />
            )}
            {hasTasks && (
              <box onMouseDown={() => setExpanded((v) => !v)}>
                <text>
                  <span fg={colors.text.disabled}>{` · ${backgroundTaskCount} background `}</span>
                  <span fg={colors.footer}>{expanded ? "ctrl+x stop · ctrl+b hide" : "ctrl+b"}</span>
                </text>
              </box>
            )}
          </box>
          {isStreaming && (
            <box flexDirection="row" gap={2}>
              <text>
                <span fg={colors.footer}>ctrl+o</span>
                <span fg={colors.text.disabled}> background</span>
              </text>
              <text>
                <span fg={colors.footer}>esc</span>
                <span fg={colors.text.disabled}> interrupt</span>
              </text>
            </box>
          )}
        </box>
      </box>
    );
  }

  return (
    <box flexDirection="column">
      {expanded && hasTaskDetails && <TaskDetails tasks={backgroundTasks} onCancel={onCancelBackgroundTask} />}
      <box flexDirection="row" justifyContent="space-between">
        <box flexDirection="row" marginLeft={3}>
          {hasTasks ? (
            <box onMouseDown={() => setExpanded((v) => !v)}>
              <text>
                <span fg={colors.text.disabled}>{backgroundTaskCount} {backgroundTaskCount === 1 ? "task" : "tasks"} in background </span>
                <span fg={colors.footer}>ctrl+b</span>
              </text>
            </box>
          ) : indexStatus?.indexing || indexStatus?.reembedding ? (
            <box flexDirection="row" gap={1}>
              <BrailleSort width={8} color={accentValue} interval={40} />
              <text><span fg={colors.text.muted}>{indexStatus.reembedding ? "re-embedding" : "indexing"}</span></text>
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
        <box gap={2} flexDirection="row">
          <text>
            <span fg={colors.footer}>ctrl+n</span>
            <span fg={colors.text.disabled}> new chat</span>
          </text>
          <text>
            <span fg={colors.footer}>ctrl+l</span>
            <span fg={colors.text.disabled}> sidebar</span>
          </text>
          <text>
            <span fg={colors.footer}>ctrl+t</span>
            <span fg={colors.text.disabled}> reasoning</span>
          </text>
          <text>
            <span fg={colors.footer}>tab tab</span>
            <span fg={colors.text.disabled}> approvals</span>
          </text>
          <text>
            <span fg={colors.footer}>shift+tab</span>
            <span fg={colors.text.disabled}> switch chat</span>
          </text>
        </box>
      </box>
    </box>
  );
}
