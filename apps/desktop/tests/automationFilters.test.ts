import { expect, test } from "bun:test";
import type { Automation } from "@/api";
import { splitAutomationsForTabs } from "@/lib/automationFilters";

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
    auto_approve: false,
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
    task_id: "knowledge-retention",
    name: "Knowledge Retention",
    handler: "knowledge_retention",
    builtin: true,
  });

  expect(splitAutomationsForTabs([internal, user])).toEqual({
    user: [user],
    internal: [internal],
  });
});

test("treats known knowledge handlers as internal even before builtin metadata is set", () => {
  const health = automation({
    task_id: "health",
    handler: "knowledge_health",
    builtin: false,
  });

  expect(splitAutomationsForTabs([health])).toEqual({
    user: [],
    internal: [health],
  });
});

test("keeps post-mode channel automations in active list", () => {
  const channel = automation({
    task_id: "channel",
    name: "News feed",
    kind: "loop",
    read_history: false,
  });

  expect(splitAutomationsForTabs([channel])).toEqual({
    user: [channel],
    internal: [],
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
  });
});
