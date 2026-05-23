import { expect, test } from "bun:test";
import { runStatusSnapshots } from "../src/hooks/useActiveRuns.ts";

test("active run polling preserves backgrounded runs for lifecycle reduction", () => {
  expect(
    runStatusSnapshots([
      { run_id: "run-1", session_id: "session-1", status: "running" },
      { run_id: "run-bg", session_id: "session-bg", status: "backgrounded", backgrounded: true },
    ]),
  ).toEqual([
    { runId: "run-1", sessionId: "session-1", status: "running", backgrounded: undefined },
    { runId: "run-bg", sessionId: "session-bg", status: "backgrounded", backgrounded: true },
  ]);
});
