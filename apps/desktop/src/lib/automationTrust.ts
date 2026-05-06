import type { Automation } from "../api";

export type AutomationTrustTone = "neutral" | "accent" | "bad";

export function automationTrustLabel(automation: Automation): string | null {
  if (automation.handler === "memory_maintenance") return "review-only";
  if (automation.handler === "memory_health") return "read-only";
  if (automation.handler === "chat_extraction" || automation.handler === "consolidation") return "writes memory";
  if (automation.writable) return "can write";
  return null;
}

export function automationTrustTone(automation: Automation): AutomationTrustTone {
  if (automation.handler === "memory_maintenance" || automation.handler === "memory_health") return "neutral";
  if (automation.writable) return "bad";
  return "accent";
}
