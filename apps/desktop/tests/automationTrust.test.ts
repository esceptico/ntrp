import { expect, test } from "bun:test";
import type { Automation } from "@/api";
import { automationTrustLabel, automationTrustTone } from "@/lib/automationTrust";

function automation(patch: Partial<Automation>): Automation {
  return {
    task_id: "task",
    name: "Task",
    description: "",
    model: null,
    triggers: [],
    enabled: false,
    created_at: "2026-05-07T00:00:00Z",
    last_run_at: null,
    next_run_at: null,
    last_result: null,
    auto_approve: false,
    running_since: null,
    handler: null,
    builtin: false,
    cooldown_minutes: null,
    ...patch,
  };
}

test("labels internal knowledge automation trust level", () => {
  expect(automationTrustLabel(automation({ handler: "knowledge_health" }))).toBe("read-only");
  expect(automationTrustLabel(automation({ handler: "knowledge_retention" }))).toBe("retention");
  expect(automationTrustLabel(automation({ handler: "knowledge_reflection" }))).toBe("learns context");
});

test("marks generic auto-approve automations as higher trust", () => {
  const writable = automation({ auto_approve: true });

  expect(automationTrustLabel(writable)).toBe("auto-approve");
  expect(automationTrustTone(writable)).toBe("bad");
});
