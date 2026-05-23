import { expect, test } from "bun:test";
import {
  claimCompactionToastForTest,
  resetCompactionToastClaimsForTest,
} from "../src/components/CompactionIndicator.tsx";

test("claims each compaction toast only once per session", () => {
  resetCompactionToastClaimsForTest();
  const compaction = { before: 120, after: 24, at: 12345 };

  expect(claimCompactionToastForTest("session-1", compaction)).toBe(true);
  expect(claimCompactionToastForTest("session-1", compaction)).toBe(false);
  expect(claimCompactionToastForTest("session-2", compaction)).toBe(true);
  expect(claimCompactionToastForTest("session-1", { ...compaction, at: 12346 })).toBe(true);
});
