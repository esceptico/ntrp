import { expect, test } from "bun:test";
import { canSaveCustomModelDraft, defaultCustomModelDraft } from "@/features/settings/lib/customModelDraft";

test("requires a model id, base URL, and positive limits before saving", () => {
  expect(canSaveCustomModelDraft(defaultCustomModelDraft())).toBe(false);

  expect(
    canSaveCustomModelDraft({
      model_id: "local/qwen",
      base_url: "http://localhost:11434/v1",
      context_window: 8192,
      max_output_tokens: 4096,
      api_key: "",
    }),
  ).toBe(true);
});
