import { expect, test } from "bun:test";
import {
  backgroundAgentKey,
  createBackgroundAgentsDomainState,
  reduceBackgroundAgentUpsert,
  reduceBackgroundAgentsDismissedByParent,
  type BackgroundAgentsDomainState,
} from "../src/store/background-agent-domain.ts";

function withAgent(
  state: BackgroundAgentsDomainState,
  sessionId: string,
  taskId: string,
  parentToolCallId: string | undefined,
): BackgroundAgentsDomainState {
  return reduceBackgroundAgentUpsert(state, {
    taskId,
    sessionId,
    command: "Agent",
    status: "completed",
    parentToolCallId,
    updatedAt: 1,
  });
}

test("dismissing by parent removes only that workflow's leaf agents", () => {
  let state = createBackgroundAgentsDomainState();
  state = withAgent(state, "sess-1", "t1", "wf-tool");
  state = withAgent(state, "sess-1", "t2", "wf-tool");
  state = withAgent(state, "sess-1", "t3", "other-tool");

  const next = reduceBackgroundAgentsDismissedByParent(state, "sess-1", "wf-tool");

  expect(Object.keys(next.rows)).toEqual([backgroundAgentKey("sess-1", "t3")]);
});

test("dismissing by parent is scoped to the session", () => {
  let state = createBackgroundAgentsDomainState();
  state = withAgent(state, "sess-1", "t1", "wf-tool");
  state = withAgent(state, "sess-2", "t1", "wf-tool");

  const next = reduceBackgroundAgentsDismissedByParent(state, "sess-1", "wf-tool");

  expect(Object.keys(next.rows)).toEqual([backgroundAgentKey("sess-2", "t1")]);
});

test("dismissing by parent prunes matching openItemIds", () => {
  let state = createBackgroundAgentsDomainState();
  state = withAgent(state, "sess-1", "t1", "wf-tool");
  state = { ...state, openItemIds: new Set([backgroundAgentKey("sess-1", "t1")]) };

  const next = reduceBackgroundAgentsDismissedByParent(state, "sess-1", "wf-tool");

  expect(next.openItemIds.size).toBe(0);
});

test("agents that never belonged to a workflow are untouched (undefined parent)", () => {
  let state = createBackgroundAgentsDomainState();
  state = withAgent(state, "sess-1", "t1", undefined);

  const next = reduceBackgroundAgentsDismissedByParent(state, "sess-1", "wf-tool");

  expect(next).toBe(state);
});

test("no match returns the same state reference (cheap no-op)", () => {
  let state = createBackgroundAgentsDomainState();
  state = withAgent(state, "sess-1", "t1", "wf-tool");

  const next = reduceBackgroundAgentsDismissedByParent(state, "sess-1", "absent-tool");

  expect(next).toBe(state);
});
