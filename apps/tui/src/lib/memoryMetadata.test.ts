import { expect, test } from "bun:test";
import { memoryMetadataRows } from "./memoryMetadata.js";

test("summarizes metadata without raw ids or json", () => {
  const rows = memoryMetadataRows({
    source_event_id: 42,
    has_context: true,
    injected_fact_ids: [5238, 5233],
    nested: { query: "test", ranker: "combined" },
  });

  expect(rows).toContainEqual({ label: "Has Context", value: "yes" });
  expect(rows).toContainEqual({ label: "Injected Fact", value: "2 records" });
  expect(rows).toContainEqual({ label: "Nested", value: "2 fields loaded" });
  expect(rows.some((row) => row.value.includes("5238") || row.value.includes("{"))).toBe(false);
  expect(rows.some((row) => row.label === "Source Event")).toBe(false);
});
