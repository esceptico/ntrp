import { expect, test } from "bun:test";
import type { ServerConfig } from "../api/client.js";
import { nextReasoningEffort, parseReasoningEffortArg, reasoningEfforts } from "./reasoning.js";

const config: ServerConfig = {
  config_version: 1,
  config_loaded_at: "2026-04-30T00:00:00Z",
  chat_model: "gpt-5.2",
  research_model: "gpt-5.2",
  memory_model: "gpt-5.2",
  embedding_model: "text-embedding-3-small",
  reasoning_effort: null,
  reasoning_efforts: ["minimal", "low", "medium", "high"],
  web_search: "auto",
  web_search_provider: "none",
  google_enabled: false,
  max_depth: 8,
  compression_threshold: 0.8,
  max_messages: 120,
  compression_keep_ratio: 0.2,
  summary_max_tokens: 1500,
  consolidation_interval: 30,
  memory_enabled: false,
};

test("cycles reasoning variants and returns to default", () => {
  expect(nextReasoningEffort(config)).toBe("minimal");
  expect(nextReasoningEffort({ ...config, reasoning_effort: "minimal" })).toBe("low");
  expect(nextReasoningEffort({ ...config, reasoning_effort: "high" })).toBeNull();
});

test("parses explicit reasoning command values", () => {
  expect(parseReasoningEffortArg(config, "HIGH")).toBe("high");
  expect(parseReasoningEffortArg(config, "default")).toBeNull();
  expect(parseReasoningEffortArg(config, "bogus")).toBeUndefined();
});

test("handles config responses without reasoning metadata", () => {
  const legacy = { ...config, reasoning_effort: undefined, reasoning_efforts: undefined };
  expect(reasoningEfforts(legacy)).toEqual([]);
  expect(nextReasoningEffort(legacy)).toBeNull();
});

test("falls back for opus 4.7 when server metadata is missing", () => {
  const legacy = { ...config, chat_model: "claude-opus-4-7", reasoning_efforts: undefined };
  expect(reasoningEfforts(legacy)).toEqual(["low", "medium", "high", "xhigh", "max"]);
  expect(nextReasoningEffort(legacy)).toBe("low");
});
