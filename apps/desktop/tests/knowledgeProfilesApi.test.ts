import { afterEach, expect, test } from "bun:test";
import { synthesizeKnowledgeProfilesApi } from "../src/api.ts";

const originalWindow = (globalThis as typeof globalThis & { window?: unknown }).window;

afterEach(() => {
  (globalThis as typeof globalThis & { window?: unknown }).window = originalWindow;
});

test("synthesizeKnowledgeProfilesApi refreshes generated profiles with limits and explicit names", async () => {
  let request: { path: string; method?: string; body?: string } | null = null;
  (globalThis as typeof globalThis & { window?: unknown }).window = {
    ntrpDesktop: {
      api: {
        request: async (_config: unknown, req: typeof request) => {
          request = req;
          return {
            ok: true,
            status: 200,
            statusText: "OK",
            contentType: "application/json",
            data: { profiles: [], skipped: 0, policy_version: "knowledge.profiles.trimem.v1" },
            text: "",
          };
        },
      },
    },
  };

  await synthesizeKnowledgeProfilesApi(
    { serverUrl: "http://localhost:6877", apiKey: "" },
    { apply: false, entity_names: ["Dex", "Regina Lin"], limit_entities: 2, evidence_limit: 8 },
  );

  expect(request).toEqual({
    path: "/knowledge/processors/profiles",
    method: "POST",
    timeout: 60000,
    body: JSON.stringify({
      apply: true,
      entity_names: ["Dex", "Regina Lin"],
      limit_entities: 2,
      evidence_limit: 8,
    }),
  });
});
