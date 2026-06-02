import type { Automation } from "../api";

export interface AutomationTabGroups {
  user: Automation[];
  internal: Automation[];
}

const INTERNAL_HANDLERS = new Set(["knowledge_reflection", "knowledge_retention", "knowledge_health"]);

export function isInternalAutomation(automation: Automation): boolean {
  return automation.builtin || (automation.handler != null && INTERNAL_HANDLERS.has(automation.handler));
}

/** Post-mode loops are still automations, but their activity lands in a
 *  channel session. They stay in Active with a channel badge/link. */
export function isChannelAutomation(automation: Automation): boolean {
  return automation.kind === "loop" && automation.read_history === false;
}

export function isIterationLoop(automation: Automation): boolean {
  return automation.kind === "loop" && automation.read_history !== false;
}

export function splitAutomationsForTabs(automations: Automation[]): AutomationTabGroups {
  const user: Automation[] = [];
  const internal: Automation[] = [];

  for (const automation of automations) {
    if (isIterationLoop(automation)) {
      // Surfaced by the Composer LoopStatusBar — hide from the panel.
      continue;
    }
    if (isInternalAutomation(automation)) {
      internal.push(automation);
    } else {
      user.push(automation);
    }
  }

  return { user, internal };
}
