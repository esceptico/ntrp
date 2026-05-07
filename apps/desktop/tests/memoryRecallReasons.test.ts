import { expect, test } from "bun:test";
import { memoryRecallReasonLabel } from "../src/lib/memoryRecallReasons.js";

test("labels recall reasons for search inspection", () => {
  expect(memoryRecallReasonLabel("fact_match")).toBe("Fact matched query");
  expect(memoryRecallReasonLabel("source_fact_match")).toBe("Source fact matched query");
  expect(memoryRecallReasonLabel("unknown_reason")).toBe("unknown_reason");
});
