import { expect, test } from "bun:test";
import type { ServerConfig } from "../api/client.js";
import { agentSettingsFromServerConfig } from "./useSettings.js";

const serverConfig: ServerConfig = {
  config_version: 7,
  config_loaded_at: "2026-04-30T00:00:00Z",
  chat_model: "openai/gpt-5.4",
  research_model: "openai/gpt-5.4",
  memory_model: "openai/gpt-5.4-mini",
  embedding_model: "text-embedding-3-large",
  reasoning_effort: "high",
  reasoning_efforts: ["low", "medium", "high"],
  web_search: "auto",
  web_search_provider: "exa",
  google_enabled: false,
  max_depth: 6,
  compression_threshold: 0.75,
  max_messages: 90,
  compression_keep_ratio: 0.25,
  summary_max_tokens: 1200,
  consolidation_interval: 20,
  memory_enabled: true,
};

test("maps backend agent config to UI settings", () => {
  expect(agentSettingsFromServerConfig(serverConfig)).toEqual({
    maxDepth: 6,
    reasoningEffort: "high",
    compressionThreshold: 75,
    maxMessages: 90,
    compressionKeepRatio: 25,
    summaryMaxTokens: 1200,
    consolidationInterval: 20,
  });
});
