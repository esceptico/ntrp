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

  expect(items).toContain('"directive" | "fact" | "source"');
  expect(api).toContain('record_count: number | null');
  expect(api).toContain('snippet: string | null');
  expect(api).toContain('generated: boolean');
  expect(api).toContain('editable: boolean');
  expect(api).toContain('readonly_reason: string | null');
  expect(api).toContain('q: params.q');

  expect(view).toContain('record_count !== null');
  expect(view).toContain('Copy path');
  expect(view).toContain('navigator.clipboard');
  expect(view).toContain('setServerQuery');
  expect(view).toContain('buildArtifactTree');
  expect(view).toContain('isMissingArtifactError');
  expect(view).toContain('setArtifacts((prev) => prev.filter');
  expect(view).toContain('const DIRECTORY_ORDER = ["memory", "context", "facts", "entities", "projects", "references", "changelog"]');
  expect(view).toContain('DEFAULT_EXPANDED_DIRS');
  expect(view).toContain('collectDefaultFolderPaths');
  expect(view).toContain('artifactAliasMap');
  expect(view).toContain('preferredAlias');
  expect(view).toContain('entities/${slug}.md');
  expect(view).toContain('setContentNotice');
  expect(view).toContain('refreshed the list');
  expect(view).not.toContain('"sources", "files", "docs"');
  expect(view).not.toContain('Fact shards');
});
