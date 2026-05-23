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
