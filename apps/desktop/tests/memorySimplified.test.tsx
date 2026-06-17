import { expect, test } from "bun:test";
import { readFileSync } from "node:fs";

test("memory modal uses the directory-first artifact browser instead of pane tabs", () => {
  const modal = readFileSync(new URL("../src/components/MemoryModal.tsx", import.meta.url), "utf8");
  const pane = readFileSync(new URL("../src/components/memory/MemoryPane.tsx", import.meta.url), "utf8");

  expect(modal).toContain("<MemoryPane />");
  expect(modal).not.toContain("MEMORY_TABS");
  expect(modal).not.toContain("<Tabs");
  expect(pane).toContain("ArtifactMemoryView");
  expect(pane).not.toContain("GraphView");
  expect(pane).not.toContain("LensesView");
});

test("artifact memory browser reflects filesystem v3 tree contracts", () => {
  const view = readFileSync(new URL("../src/components/memory/ArtifactMemoryView.tsx", import.meta.url), "utf8");
  const api = readFileSync(new URL("../src/api/memoryArtifacts.ts", import.meta.url), "utf8");
  const items = readFileSync(new URL("../src/api/memoryItems.ts", import.meta.url), "utf8");

  expect(items).toContain('"dossier"');
  expect(api).toContain('record_count: number | null');
  expect(api).toContain('snippet: string | null');
  expect(api).toContain('generated: boolean');
  expect(api).toContain('editable: boolean');
  expect(api).toContain('readonly_reason: string | null');
  expect(api).toContain('q: params.q');

  expect(view).toContain('entities: { title: "entities/", subtitle: "Emergent dossiers and triage" }');
  expect(view).toContain('dossier: "Generated entity/project briefs"');
  expect(view).toContain('record_count !== null');
  expect(view).toContain('DB-backed facts');
  expect(view).toContain('Copy path');
  expect(view).toContain('navigator.clipboard');
  expect(view).toContain('setServerQuery');
  expect(view).toContain('buildArtifactTree');
  expect(view).not.toContain('Fact shards');
});
