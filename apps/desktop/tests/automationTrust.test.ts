import { expect, test } from "bun:test";
import type { Automation } from "../src/api";
import { automationTrustLabel, automationTrustTone } from "../src/lib/automationTrust.js";

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
    writable: false,
    running_since: null,
    handler: null,
    builtin: false,
    cooldown_minutes: null,
    ...patch,
  };
}

test("labels internal memory automation trust level", () => {
  expect(automationTrustLabel(automation({ handler: "memory_maintenance" }))).toBe("review-only");
  expect(automationTrustLabel(automation({ handler: "memory_health" }))).toBe("read-only");
  expect(automationTrustLabel(automation({ handler: "chat_extraction" }))).toBe("writes memory");
  expect(automationTrustLabel(automation({ handler: "consolidation" }))).toBe("writes memory");
});

test("marks generic writable automations as higher trust", () => {
  const writable = automation({ writable: true });

  expect(automationTrustLabel(writable)).toBe("can write");
  expect(automationTrustTone(writable)).toBe("bad");
});
