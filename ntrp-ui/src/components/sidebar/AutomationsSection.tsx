import React, { useEffect, useRef, useState } from "react";
import { truncateText } from "../../lib/utils.js";
import type { Automation } from "../../api/client.js";
import { connectAutomationEvents, type AutomationEvent } from "../../api/automations.js";
import { formatCountdown, triggersLabel } from "../../lib/format.js";
import { SectionHeader, D, S } from "./shared.js";
import { colors } from "../ui/colors.js";

interface Progress {
  status: string;
  done?: boolean;
}

function useAutomationProgress(automations: Automation[], serverUrl: string) {
  const [progress, setProgress] = useState<Map<string, Progress>>(new Map());
  const disconnects = useRef<Map<string, () => void>>(new Map());

  useEffect(() => {
    const running = new Set(
      automations.filter(a => a.running_since && !a.builtin).map(a => a.task_id),
    );

    // Connect to newly running automations
    for (const taskId of running) {
      if (disconnects.current.has(taskId)) continue;

      setProgress(prev => {
        const next = new Map(prev);
        next.set(taskId, { status: "starting..." });
        return next;
      });

      const disconnect = connectAutomationEvents(
        taskId,
        { serverUrl },
        (event: AutomationEvent) => {
          if (event.type === "tool_call") {
            const label = event.display_name || event.name || "working";
            setProgress(prev => {
              const next = new Map(prev);
              next.set(taskId, { status: `${label}...` });
              return next;
            });
          } else if (event.type === "tool_result") {
            const label = event.display_name || event.name || "";
            const preview = event.preview || "";
            setProgress(prev => {
              const next = new Map(prev);
              next.set(taskId, { status: preview ? `${label}: ${preview}` : label });
              return next;
            });
          } else if (event.type === "text") {
            setProgress(prev => {
              const next = new Map(prev);
              next.set(taskId, { status: event.content || "", done: true });
              return next;
            });
          }
        },
      );
      disconnects.current.set(taskId, disconnect);
    }

    // Cleanup automations that stopped running
    for (const [taskId, disconnect] of disconnects.current) {
      if (!running.has(taskId)) {
        disconnect();
        disconnects.current.delete(taskId);
        // Show "done" briefly, then clear
        setProgress(prev => {
          const entry = prev.get(taskId);
          if (!entry?.done) {
            const next = new Map(prev);
            next.set(taskId, { ...entry, status: entry?.status || "done", done: true });
            return next;
          }
          return prev;
        });
        setTimeout(() => {
          setProgress(prev => {
            const next = new Map(prev);
            next.delete(taskId);
            return next;
          });
        }, 5000);
      }
    }

    return () => {
      for (const disconnect of disconnects.current.values()) disconnect();
      disconnects.current.clear();
    };
  }, [automations, serverUrl]);

  return progress;
}

function AutomationRow({
  automation,
  width,
  progress,
}: {
  automation: Automation;
  width: number;
  progress?: Progress;
}) {
  const name = automation.name || automation.description;

  if (progress?.done) {
    const statusWidth = Math.max(4, width - 2 - 2);
    return (
      <box flexDirection="column">
        <text>
          <span fg={colors.status.success}>{"✓ "}</span>
          <span fg={S()}>{truncateText(name, width - 2)}</span>
        </text>
        <text>
          <span fg={D()}>{"  ┊ "}</span>
          <span fg={D()}>{truncateText(progress.status, statusWidth)}</span>
        </text>
      </box>
    );
  }

  if (progress) {
    const statusWidth = Math.max(4, width - 2 - 2);
    return (
      <box flexDirection="column">
        <text>
          <span fg={colors.tool.running}>{"▶ "}</span>
          <span fg={S()}>{truncateText(name, width - 2)}</span>
        </text>
        <text>
          <span fg={D()}>{"  ┊ "}</span>
          <span fg={D()}>{truncateText(progress.status, statusWidth)}</span>
        </text>
      </box>
    );
  }

  const time = triggersLabel(automation.triggers, true);
  const eta = automation.next_run_at ? formatCountdown(automation.next_run_at) : "";
  const prefix = `${time} `;
  const suffix = eta ? ` ${eta}` : "";
  const nameWidth = Math.max(4, width - prefix.length - suffix.length);

  return (
    <text>
      <span fg={D()}>{prefix}</span>
      <span fg={S()}>{truncateText(name, nameWidth)}</span>
      {suffix && <span fg={D()}>{suffix}</span>}
    </text>
  );
}

export function AutomationsSection({
  automations,
  width,
  serverUrl,
}: {
  automations: Automation[];
  width: number;
  serverUrl: string;
}) {
  const userAutomations = automations.filter(a => !a.builtin);
  const progress = useAutomationProgress(userAutomations, serverUrl);

  if (userAutomations.length === 0) return null;

  return (
    <box flexDirection="column">
      <SectionHeader label="NEXT UP" />
      {userAutomations.map(s => (
        <AutomationRow
          key={s.task_id}
          automation={s}
          width={width}
          progress={progress.get(s.task_id)}
        />
      ))}
    </box>
  );
}
