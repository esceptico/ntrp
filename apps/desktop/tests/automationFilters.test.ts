import { expect, test } from "bun:test";
import type { Automation } from "../src/api";
import { splitAutomationsForTabs } from "../src/lib/automationFilters.js";

function automation(patch: Partial<Automation>): Automation {
  return {
    task_id: "task",
    name: "Automation",
    description: "",
    model: null,
    triggers: [],
    enabled: true,
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

test("keeps user automations separate from internal automations", () => {
  const user = automation({ task_id: "user", name: "Daily brief" });
  const internal = automation({
    task_id: "memory-maintenance",
    name: "Memory Maintenance",
    handler: "memory_maintenance",
    builtin: true,
  });

  expect(splitAutomationsForTabs([internal, user])).toEqual({
    user: [user],
    internal: [internal],
    channels: [],
  });
});

test("treats known memory handlers as internal even before builtin metadata is set", () => {
  const maintenance = automation({
    task_id: "maintenance",
    handler: "memory_health",
    builtin: false,
  });

  expect(splitAutomationsForTabs([maintenance])).toEqual({
    user: [],
    internal: [maintenance],
    channels: [],
  });
});

test("routes post-mode loop to channels bucket", () => {
  const channel = automation({
    task_id: "channel",
    name: "News feed",
    kind: "loop",
    read_history: false,
  });

  expect(splitAutomationsForTabs([channel])).toEqual({
    user: [],
    internal: [],
    channels: [channel],
  });
});

test("drops iteration loops from all buckets", () => {
  const iteration = automation({
    task_id: "iteration",
    name: "Self-paced loop",
    kind: "loop",
    read_history: true,
  });

  expect(splitAutomationsForTabs([iteration])).toEqual({
    user: [],
    internal: [],
    channels: [],
  });
});
