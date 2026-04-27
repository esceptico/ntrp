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

function useAutomationProgress(serverUrl: string) {
  const [progress, setProgress] = useState<Map<string, Progress>>(new Map());
  const timers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  useEffect(() => {
    const disconnect = connectAutomationEvents(
      { serverUrl },
      (event: AutomationEvent) => {
        if (event.type === "automation_progress") {
          setProgress(prev => {
            const next = new Map(prev);
            next.set(event.task_id, { status: event.status || "working..." });
            return next;
          });
        } else if (event.type === "automation_finished") {
          // Clear any existing done timer
          const existing = timers.current.get(event.task_id);
          if (existing) clearTimeout(existing);

          const result = event.result;
          setProgress(prev => {
            const next = new Map(prev);
            next.set(event.task_id, {
              status: result ? truncateText(result, 60) : "done",
              done: true,
            });
            return next;
          });

          const timer = setTimeout(() => {
            timers.current.delete(event.task_id);
            setProgress(prev => {
              const next = new Map(prev);
              next.delete(event.task_id);
              return next;
            });
          }, 5000);
          timers.current.set(event.task_id, timer);
        }
      },
    );

    return () => {
      disconnect();
      for (const timer of timers.current.values()) clearTimeout(timer);
      timers.current.clear();
    };
  }, [serverUrl]);

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

  if (progress) {
    const icon = progress.done ? "✓ " : "▶ ";
    const iconColor = progress.done ? colors.status.success : colors.tool.running;
    const statusWidth = Math.max(4, width - 4);
    return (
      <box flexDirection="column">
        <text>
          <span fg={iconColor}>{icon}</span>
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
  const progress = useAutomationProgress(serverUrl);

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
