import type { Automation } from "@/api";

export type AutomationTrustTone = "neutral" | "accent" | "bad";

export function automationTrustLabel(automation: Automation): string | null {
  if (automation.handler === "knowledge_health") return "read-only";
  if (automation.handler === "knowledge_retention") return "retention";
  if (automation.handler === "knowledge_reflection") return "learns context";
  if (automation.auto_approve) return "auto-approve";
  return null;
}

export function automationTrustTone(automation: Automation): AutomationTrustTone {
  if (automation.handler?.startsWith("knowledge_")) return "neutral";
  if (automation.auto_approve) return "bad";
  return "accent";
}
