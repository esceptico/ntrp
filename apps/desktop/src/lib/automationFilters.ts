import type { Automation } from "../api";

export interface AutomationTabGroups {
  user: Automation[];
  internal: Automation[];
  channels: Automation[];
}

const INTERNAL_HANDLERS = new Set(["chat_extraction", "consolidation", "memory_maintenance", "memory_health"]);

export function isInternalAutomation(automation: Automation): boolean {
  return automation.builtin || (automation.handler != null && INTERNAL_HANDLERS.has(automation.handler));
}

/** Post-mode loops (read_history=false) emit to a fresh channel session
 *  each tick — they're feeds, not chat automations. Iteration loops
 *  (read_history=true) are surfaced live in the Composer chip, so they
 *  don't belong in either list. */
export function isChannelAutomation(automation: Automation): boolean {
  return automation.kind === "loop" && automation.read_history === false;
}

export function isIterationLoop(automation: Automation): boolean {
  return automation.kind === "loop" && automation.read_history !== false;
}

export function splitAutomationsForTabs(automations: Automation[]): AutomationTabGroups {
  const user: Automation[] = [];
  const internal: Automation[] = [];
  const channels: Automation[] = [];

  for (const automation of automations) {
    if (isIterationLoop(automation)) {
      // Surfaced by the Composer LoopStatusBar — hide from the panel.
      continue;
    }
    if (isChannelAutomation(automation)) {
      channels.push(automation);
      continue;
    }
    if (isInternalAutomation(automation)) {
      internal.push(automation);
    } else {
      user.push(automation);
    }
  }

  return { user, internal, channels };
}
