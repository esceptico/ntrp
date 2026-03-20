import React from "react";
import { truncateText } from "../../lib/utils.js";
import type { Automation } from "../../api/client.js";
import { formatCountdown, triggersLabel } from "../../lib/format.js";
import { SectionHeader, D, S } from "./shared.js";

function AutomationRow({ automation, width }: { automation: Automation; width: number }) {
  const time = triggersLabel(automation.triggers, true);
  const eta = automation.next_run_at ? formatCountdown(automation.next_run_at) : "";
  const prefix = `${time} `;
  const suffix = eta ? ` ${eta}` : "";
  const nameWidth = Math.max(4, width - prefix.length - suffix.length);
  const name = truncateText(automation.name || automation.description, nameWidth);

  return (
    <text>
      <span fg={D()}>{prefix}</span>
      <span fg={S()}>{name}</span>
      {suffix && <span fg={D()}>{suffix}</span>}
    </text>
  );
}

export function AutomationsSection({ automations, width }: { automations: Automation[]; width: number }) {
  const userAutomations = automations.filter(a => !a.builtin);
  if (userAutomations.length === 0) return null;

  return (
    <box flexDirection="column">
      <SectionHeader label="NEXT UP" />
      {userAutomations.map(s => (
        <AutomationRow key={s.task_id} automation={s} width={width} />
      ))}
    </box>
  );
}
