import { expect, test } from "bun:test";
import { readFileSync } from "node:fs";

test("memory modal uses the directory-first artifact browser instead of pane tabs", () => {
  const modal = readFileSync(new URL("../src/features/memory/components/MemoryModal.tsx", import.meta.url), "utf8");
  const pane = readFileSync(new URL("../src/features/memory/components/MemoryPane.tsx", import.meta.url), "utf8");

  expect(modal).toContain("<MemoryPane />");
  expect(modal).not.toContain("MEMORY_TABS");
  expect(modal).not.toContain("<Tabs");
  expect(pane).toContain("ArtifactMemoryView");
  expect(pane).not.toContain("GraphView");
  expect(pane).not.toContain("LensesView");
});

test("artifact memory browser reflects filesystem v3 tree contracts", () => {
  const view = readFileSync(new URL("../src/features/memory/components/ArtifactMemoryView.tsx", import.meta.url), "utf8");
  const api = readFileSync(new URL("../src/api/memoryArtifacts.ts", import.meta.url), "utf8");
  const items = readFileSync(new URL("../src/api/memoryItems.ts", import.meta.url), "utf8");
  const tree = readFileSync(new URL("../src/features/memory/lib/artifactTree.ts", import.meta.url), "utf8");
  const copyPath = readFileSync(new URL("../src/features/memory/components/CopyPath.tsx", import.meta.url), "utf8");

  expect(items).toContain('"directive" | "fact" | "source"');
  expect(api).toContain('record_count: number | null');
  expect(api).toContain('snippet: string | null');
  expect(api).toContain('generated: boolean');
  expect(api).toContain('editable: boolean');
  expect(api).toContain('readonly_reason: string | null');
  expect(api).toContain('q: params.q');

  // Copy-path UX feature lives in CopyPath.tsx.
  expect(copyPath).toContain('Copy path');
  expect(copyPath).toContain('navigator.clipboard');

  // Folder order + no old structure are the genuine v3 contracts, in artifactTree.ts.
  expect(tree).toContain('const DIRECTORY_ORDER = ["topics", "daily", "insights", "observations", "context", "facts", "changelog"]');
  expect(tree).not.toContain('"sources", "files", "docs"');
  expect(tree).not.toContain('Fact shards');

  // Missing-artifact recovery notice still surfaces from the orchestrator.
  expect(view).toContain('refreshed the list');
});
