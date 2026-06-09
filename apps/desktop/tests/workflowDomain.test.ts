import { expect, test } from "bun:test";
import {
  createWorkflowsDomainState,
  reduceWorkflowDismissed,
  reduceWorkflowStarted,
  reduceWorkflowFinished,
  reduceWorkflowTaskEvent,
  reduceWorkflowTokenUsage,
  selectWorkflowsForSession,
  workflowKey,
} from "../src/store/workflow-domain.ts";

const SESSION = "session-1";
const WORKFLOW = "wf-1";

function startedWorkflow(now = 1000) {
  return reduceWorkflowStarted(
    createWorkflowsDomainState(),
    { workflowId: WORKFLOW, sessionId: SESSION, runId: "run-1", name: "Research" },
    now,
  );
}

test("workflow_started creates a workflow keyed by session + workflow id", () => {
  const state = startedWorkflow(1000);
  const workflow = state.rows[workflowKey(SESSION, WORKFLOW)];

  expect(workflow).toBeDefined();
  expect(workflow.workflowId).toBe(WORKFLOW);
  expect(workflow.sessionId).toBe(SESSION);
  expect(workflow.runId).toBe("run-1");
  expect(workflow.name).toBe("Research");
  expect(workflow.status).toBe("running");
  expect(workflow.startedAt).toBe(1000);
  expect(Object.keys(workflow.phasesByName)).toHaveLength(0);
});

test("tagged task_started then task_finished create and settle an agent under its phase", () => {
  let state = startedWorkflow(1000);

  state = reduceWorkflowTaskEvent(
    state,
    {
      kind: "started",
      workflowId: WORKFLOW,
      sessionId: SESSION,
      taskId: "task-a",
      phase: "gather",
      name: "Gatherer",
      agentType: "research",
    },
    2000,
  );

  let phase = state.rows[workflowKey(SESSION, WORKFLOW)].phasesByName.gather;
  expect(phase).toBeDefined();
  expect(phase.status).toBe("running");
  expect(phase.startedAt).toBe(2000);
  let agent = phase.agentsByTaskId["task-a"];
  expect(agent.status).toBe("running");
  expect(agent.phase).toBe("gather");
  expect(agent.name).toBe("Gatherer");
  expect(agent.agentType).toBe("research");
  expect(agent.startedAt).toBe(2000);
  expect(agent.completedAt).toBeUndefined();

  state = reduceWorkflowTaskEvent(
    state,
    {
      kind: "finished",
      workflowId: WORKFLOW,
      sessionId: SESSION,
      taskId: "task-a",
      phase: "gather",
      status: "completed",
    },
    5000,
  );

  phase = state.rows[workflowKey(SESSION, WORKFLOW)].phasesByName.gather;
  agent = phase.agentsByTaskId["task-a"];
  expect(agent.status).toBe("completed");
  expect(agent.completedAt).toBe(5000);
  expect(agent.durationMs).toBe(3000);
  // identity preserved from task_started across the finish
  expect(agent.name).toBe("Gatherer");
  expect(phase.status).toBe("completed");
  expect(phase.completedAt).toBe(5000);
});

test("token_usage with task_id accumulates tokens and cost on the matching agent", () => {
  let state = startedWorkflow(1000);
  state = reduceWorkflowTaskEvent(
    state,
    { kind: "started", workflowId: WORKFLOW, sessionId: SESSION, taskId: "task-a", phase: "gather" },
    2000,
  );

  state = reduceWorkflowTokenUsage(
    state,
    {
      workflowId: WORKFLOW,
      sessionId: SESSION,
      taskId: "task-a",
      phase: "gather",
      usage: { prompt: 100, completion: 20, cache_read: 5 },
      cost: 0.01,
    },
    3000,
  );
  state = reduceWorkflowTokenUsage(
    state,
    {
      workflowId: WORKFLOW,
      sessionId: SESSION,
      taskId: "task-a",
      phase: "gather",
      usage: { prompt: 50, completion: 10, cache_read: 5 },
      cost: 0.02,
    },
    4000,
  );

  const agent = state.rows[workflowKey(SESSION, WORKFLOW)].phasesByName.gather.agentsByTaskId["task-a"];
  expect(agent.tokens).toEqual({
    prompt: 150,
    completion: 30,
    total: 180,
    cache_read: 10,
    cache_write: undefined,
  });
  expect(agent.cost).toBeCloseTo(0.03, 5);
});

test("token_usage for an unknown agent is a no-op", () => {
  let state = startedWorkflow(1000);
  const before = state;
  state = reduceWorkflowTokenUsage(
    state,
    {
      workflowId: WORKFLOW,
      sessionId: SESSION,
      taskId: "ghost",
      phase: "gather",
      usage: { prompt: 1, completion: 1 },
    },
    3000,
  );
  expect(state).toBe(before);
});

test("two concurrent agents under one phase do not collide", () => {
  let state = startedWorkflow(1000);

  state = reduceWorkflowTaskEvent(
    state,
    { kind: "started", workflowId: WORKFLOW, sessionId: SESSION, taskId: "task-a", phase: "gather", name: "A" },
    2000,
  );
  state = reduceWorkflowTaskEvent(
    state,
    { kind: "started", workflowId: WORKFLOW, sessionId: SESSION, taskId: "task-b", phase: "gather", name: "B" },
    2100,
  );

  state = reduceWorkflowTokenUsage(
    state,
    { workflowId: WORKFLOW, sessionId: SESSION, taskId: "task-a", phase: "gather", usage: { prompt: 10, completion: 1 } },
    2200,
  );

  // Finish only A; B stays running and the phase stays running.
  state = reduceWorkflowTaskEvent(
    state,
    { kind: "finished", workflowId: WORKFLOW, sessionId: SESSION, taskId: "task-a", phase: "gather", status: "completed" },
    3000,
  );

  const phase = state.rows[workflowKey(SESSION, WORKFLOW)].phasesByName.gather;
  const agentA = phase.agentsByTaskId["task-a"];
  const agentB = phase.agentsByTaskId["task-b"];

  expect(Object.keys(phase.agentsByTaskId)).toHaveLength(2);
  expect(agentA.status).toBe("completed");
  expect(agentA.tokens?.prompt).toBe(10);
  // B is untouched by A's events.
  expect(agentB.status).toBe("running");
  expect(agentB.name).toBe("B");
  expect(agentB.tokens).toBeUndefined();
  expect(agentB.completedAt).toBeUndefined();
  // Phase is still running and not yet completed.
  expect(phase.status).toBe("running");
  expect(phase.completedAt).toBeNull();
});

test("missing phase defaults to a single 'default' bucket", () => {
  let state = startedWorkflow(1000);
  state = reduceWorkflowTaskEvent(
    state,
    { kind: "started", workflowId: WORKFLOW, sessionId: SESSION, taskId: "task-a", phase: null },
    2000,
  );
  const workflow = state.rows[workflowKey(SESSION, WORKFLOW)];
  expect(Object.keys(workflow.phasesByName)).toEqual(["default"]);
  expect(workflow.phasesByName.default.agentsByTaskId["task-a"].phase).toBe("default");
});

test("workflow_finished settles status, summary and agent count", () => {
  let state = startedWorkflow(1000);
  state = reduceWorkflowFinished(
    state,
    { workflowId: WORKFLOW, sessionId: SESSION, status: "completed", summary: "done", agentCount: 3 },
    9000,
  );
  const workflow = state.rows[workflowKey(SESSION, WORKFLOW)];
  expect(workflow.status).toBe("completed");
  expect(workflow.summary).toBe("done");
  expect(workflow.totalAgents).toBe(3);
  expect(workflow.completedAt).toBe(9000);
});

test("task events for an unknown workflow are a no-op", () => {
  const state = createWorkflowsDomainState();
  const next = reduceWorkflowTaskEvent(
    state,
    { kind: "started", workflowId: "missing", sessionId: SESSION, taskId: "task-a", phase: "gather" },
    2000,
  );
  expect(next).toBe(state);
});

test("selectWorkflowsForSession is scoped to the session", () => {
  let state = startedWorkflow(1000);
  state = reduceWorkflowStarted(
    state,
    { workflowId: "wf-2", sessionId: "session-2", runId: "run-2" },
    1000,
  );
  expect(selectWorkflowsForSession(state, SESSION).map((w) => w.workflowId)).toEqual([WORKFLOW]);
  expect(selectWorkflowsForSession(state, "session-2").map((w) => w.workflowId)).toEqual(["wf-2"]);
  expect(selectWorkflowsForSession(state, "nope")).toHaveLength(0);
});

test("reduceWorkflowDismissed removes the row; no-op if absent", () => {
  const state = startedWorkflow();
  expect(selectWorkflowsForSession(state, SESSION)).toHaveLength(1);
  const after = reduceWorkflowDismissed(state, { sessionId: SESSION, workflowId: WORKFLOW });
  expect(selectWorkflowsForSession(after, SESSION)).toHaveLength(0);
  // dismissing an unknown id returns the same state reference (cheap no-op)
  expect(reduceWorkflowDismissed(after, { sessionId: SESSION, workflowId: "nope" })).toBe(after);
});
