import { afterEach, expect, test } from "bun:test";
import { compactSessionApi } from "../src/api.ts";

const originalWindow = (globalThis as typeof globalThis & { window?: unknown }).window;

afterEach(() => {
  (globalThis as typeof globalThis & { window?: unknown }).window = originalWindow;
});

test("compactSessionApi uses an extended timeout", async () => {
  let request: { path: string; method?: string; body?: string; timeout?: number } | null = null;
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
            data: { status: "compacted" },
            text: "",
          };
        },
      },
    },
  };

  await compactSessionApi({ serverUrl: "http://localhost:6877", apiKey: "" }, "sess-1");

  expect(request).toEqual({
    path: "/compact",
    method: "POST",
    body: JSON.stringify({ session_id: "sess-1" }),
    timeout: 180_000,
  });
});
