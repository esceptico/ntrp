import { expect, test } from "bun:test";
import { turnHasActiveChildAgent } from "@/features/chat/lib/turnActiveAgents";
import type { BackgroundAgent, UiMessage } from "@/stores/types";

test("finished parent turn stays live while a referenced child agent is active", () => {
  expect(
    turnHasActiveChildAgent({
      childIds: ["activity-1"],
      messages: new Map([["activity-1", activityMessage()]]),
      backgroundAgents: {
        "session-1:child-run-1": backgroundAgent(),
      },
      sessionId: "session-1",
    }),
  ).toBe(true);
});

test("ignores completed or unrelated child agents", () => {
  const messages = new Map<string, UiMessage>([["activity-1", activityMessage()]]);

  expect(
    turnHasActiveChildAgent({
      childIds: ["activity-1"],
      messages,
      backgroundAgents: {
        "session-1:child-run-1": backgroundAgent({ status: "completed" }),
      },
      sessionId: "session-1",
    }),
  ).toBe(false);

  expect(
    turnHasActiveChildAgent({
      childIds: ["activity-1"],
      messages,
      backgroundAgents: {
        "session-2:child-run-1": backgroundAgent({ sessionId: "session-2" }),
      },
      sessionId: "session-1",
    }),
  ).toBe(false);

  expect(
    turnHasActiveChildAgent({
      childIds: ["activity-1"],
      messages,
      backgroundAgents: {
        "session-1:other-child": backgroundAgent({
          taskId: "other-child",
          childSessionId: "other-session",
          parentToolCallId: "other-call",
        }),
      },
      sessionId: "session-1",
    }),
  ).toBe(false);
});

function activityMessage(): UiMessage {
  return {
    id: "activity-1",
    role: "activity",
    content: "",
    activity: {
      label: "Backgrounded",
      done: true,
      items: [
        {
          id: "call-agent-1",
          kind: "spawn_agent",
          semanticKind: "agent",
          target: "Research",
          childAgent: {
            childRunId: "child-run-1",
            childSessionId: "child-session-1",
            parentToolCallId: "call-agent-1",
            agentType: "research",
            wait: false,
            status: "running",
          },
        },
      ],
    },
  };
}

function backgroundAgent(overrides: Partial<BackgroundAgent> = {}): BackgroundAgent {
  return {
    taskId: "child-run-1",
    sessionId: "session-1",
    childSessionId: "child-session-1",
    command: "Research",
    status: "running",
    parentToolCallId: "call-agent-1",
    agentType: "research",
    wait: false,
    createdAt: 1,
    updatedAt: 1,
    ...overrides,
  };
}
