import { expect, test } from "bun:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { GroupedProfiles, LensHeader } from "../src/components/memory/LensesView.tsx";
import type { Lens, ProjectedGroup } from "../src/api/memoryItems.ts";

const lens: Lens = {
  id: "records",
  name: "Records",
  criterion: "approved record entries",
  entity_type: "item",
  scope: { kind: "user", key: null },
  detail_level: "structured",
  render_mode: "flat",
  provenance: "user_authored",
  status: "active",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

test("lens header keeps only the refresh action", () => {
  const html = renderToStaticMarkup(
    <LensHeader lens={lens} onRefresh={() => {}} refreshing={false} />,
  );

  expect(html).toContain('aria-label="Re-synthesize"');
  expect(html).not.toContain("Group by subject");
  expect(html).not.toContain("Provenance graph");
});

test("profile rows hide source claims by default", () => {
  const groups: ProjectedGroup[] = [
    {
      subject: "Record A",
      markdown: "- stored fact <!--claim:c1-->",
      synthesized: true,
      blocks: [
        {
          claim_id: "c1",
          content: "Stored fact A.",
          provenance: "recorded",
          corroboration: 1,
          feedback: "none",
          source_refs: [],
        },
      ],
    },
  ];

  const html = renderToStaticMarkup(
    <GroupedProfiles
      groups={groups}
      editingId={null}
      busyId={null}
      exiting={null}
      onOpen={() => {}}
      onClose={() => {}}
      onCommit={() => {}}
      onPeek={() => {}}
    />,
  );

  expect(html).toContain("Record A");
  expect(html).toContain("Sources");
  expect(html).not.toContain("Stored fact A.");
  expect(html).not.toContain("Source claim");
});
