import { expect, test } from "bun:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ActivityHeader, ActivityTail } from "../src/components/trace/ActivityTrace.tsx";
import { activityTraceStats } from "../src/lib/agent.ts";

const items = [
  {
    id: "research-1",
    kind: "research",
    semanticKind: "agent",
    target: "research",
    args: "{}",
    depth: 0,
  },
  {
    id: "tool-1",
    kind: "read_file",
    target: 'read_file(path="a")',
    args: "{}",
    depth: 1,
    parentToolId: "research-1",
  },
];

test("replayed rolling activity rows keep the motion row path disabled", () => {
  const html = renderToStaticMarkup(
    <ActivityTail items={items} max={3} motionDisabled />,
  );

  expect(html).toContain('data-activity-motion-row="true"');
  expect(html).toContain('data-motion-suppressed="true"');
});

test("activity header shows active calls separately from total calls", () => {
  const html = renderToStaticMarkup(
    <ActivityHeader label="Calling" count={816} activeCount={1} />,
  );

  expect(html).toContain("Running");
  expect(html).toContain("816");
  expect(html).toContain("calls");
  expect(html).toContain("1");
  expect(html).toContain("active");
  expect(html).toContain("inline-flex items-center gap-1 leading-none");
});

test("running agent row renders a stop control", () => {
  const html = renderToStaticMarkup(
    <ActivityTail
      items={[
        {
          id: "call-research",
          kind: "research",
          semanticKind: "agent",
          target: "research",
          status: "ongoing",
          taskStatus: "running",
          runId: "run-1",
        },
      ]}
      max={3}
      motionDisabled
    />,
  );

  expect(html).toContain("Stop subagent");
  expect(html).toContain("group-hover/agent:opacity-0");
  expect(html).toContain("group-hover/agent:opacity-100");
  expect(html).toContain("group-hover/stop:opacity-100");
});

test("generic ongoing agent row waits for lifecycle ownership before stop control", () => {
  const html = renderToStaticMarkup(
    <ActivityTail
      items={[
        {
          id: "call-research",
          kind: "research",
          semanticKind: "agent",
          target: "research",
          status: "ongoing",
        },
      ]}
      max={3}
      motionDisabled
    />,
  );

  expect(html).not.toContain("Stop subagent");
});

test("agent trace row shows generated name but not prompt text", () => {
  const html = renderToStaticMarkup(
    <ActivityTail
      items={[
        {
          id: "call-research",
          kind: "research",
          semanticKind: "agent",
          target: "research",
          args: JSON.stringify({ task: "inspect current eval/test harness opportunities" }),
          displayName: "Research Eval Test Harness",
          status: "ongoing",
        },
      ]}
      max={3}
      motionDisabled
    />,
  );

  expect(html).toContain("Research Eval Test Harness");
  expect(html).not.toContain("inspect current eval/test harness opportunities");
});

test("activity stats include subagent rows and their child tools", () => {
  expect(activityTraceStats([
    {
      id: "research-1",
      kind: "research",
      semanticKind: "agent",
      target: "research",
      status: "ongoing",
    },
    {
      id: "child-done",
      kind: "ReadFile",
      target: "ReadFile(path='a')",
      parentToolId: "research-1",
      depth: 1,
      result: "ok",
      status: "executed",
    },
    {
      id: "child-running",
      kind: "SlackSearch",
      target: "SlackSearch(query='x')",
      parentToolId: "research-1",
      depth: 1,
      status: "ongoing",
    },
  ])).toEqual({ totalCount: 3, activeCount: 2 });
});
