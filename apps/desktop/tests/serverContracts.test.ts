import { expect, test } from "bun:test";
import { parseModelsResponse, parseServerConfig } from "../src/api.js";

const config = {
  chat_model: "gpt-5.2",
  research_model: "claude-opus-4-7",
  memory_model: "gpt-5.2",
  embedding_model: "text-embedding-3-small",
  web_search: "auto",
  web_search_provider: "none",
  google_enabled: false,
  max_depth: 8,
  reasoning_effort: null,
  reasoning_efforts: ["low", "medium"],
  model_reasoning_efforts: {},
  compression_threshold: 0.8,
  max_messages: 20,
  compression_keep_ratio: 0.5,
  summary_max_tokens: 2500,
  consolidation_interval: 60,
  memory_enabled: true,
  integrations: {},
};

test("rejects stale config responses before they enter state", () => {
  const stale = { ...config };
  Reflect.deleteProperty(stale, "model_reasoning_efforts");

  expect(() => parseServerConfig(stale)).toThrow("model_reasoning_efforts");
});

test("rejects stale model metadata before it enters state", () => {
  expect(() => parseModelsResponse({
    models: ["gpt-5.2"],
    groups: [{ provider: "openai", models: ["gpt-5.2"] }],
  })).toThrow("reasoning_efforts");
});

test("accepts current config and model metadata contracts", () => {
  expect(parseServerConfig(config)).toEqual(config);
  expect(parseModelsResponse({
    models: ["gpt-5.2"],
    groups: [{ provider: "openai", models: ["gpt-5.2"] }],
    reasoning_efforts: { "gpt-5.2": ["low", "medium"] },
    chat_model: "gpt-5.2",
    research_model: "gpt-5.2",
    memory_model: "gpt-5.2",
  })).toMatchObject({ reasoning_efforts: { "gpt-5.2": ["low", "medium"] } });
});
