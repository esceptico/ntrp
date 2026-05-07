import type { Automation } from "../api";

export interface AutomationTabGroups {
  user: Automation[];
  internal: Automation[];
}

const INTERNAL_HANDLERS = new Set(["chat_extraction", "consolidation", "memory_maintenance", "memory_health"]);

export function isInternalAutomation(automation: Automation): boolean {
  return automation.builtin || (automation.handler != null && INTERNAL_HANDLERS.has(automation.handler));
}

export function splitAutomationsForTabs(automations: Automation[]): AutomationTabGroups {
  const user: Automation[] = [];
  const internal: Automation[] = [];

  for (const automation of automations) {
    if (isInternalAutomation(automation)) {
      internal.push(automation);
    } else {
      user.push(automation);
    }
  }

  return { user, internal };
}
