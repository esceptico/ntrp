import { expect, test } from "bun:test";
import {
  providerActionLabel,
  providerConnectionLabel,
  providerConnectionPill,
  providerModelCountLabel,
  providerReadinessSummary,
} from "../src/lib/providerConnection.js";

test("labels env-managed provider connections", () => {
  const provider = {
    id: "openai",
    name: "OpenAI",
    connected: true,
    from_env: true,
    auth_type: "api_key",
    key_hint: "sk-...abcd",
    models: ["gpt-5.5"],
    embedding_models: ["text-embedding-3-small"],
  } as const;

  expect(providerConnectionLabel(provider)).toBe("Connected via env");
  expect(providerActionLabel(provider)).toBe("Env-managed");
});

test("uses sign-in language for Codex OAuth", () => {
  const provider = {
    id: "openai-codex",
    name: "OpenAI Codex",
    connected: false,
    from_env: false,
    auth_type: "oauth",
    key_hint: null,
    models: ["openai-codex/gpt-5.5"],
    embedding_models: [],
  } as const;

  expect(providerConnectionLabel(provider)).toBe("Not connected");
  expect(providerConnectionPill(provider)).toBeNull();
  expect(providerActionLabel(provider)).toBe("Sign in");
});

test("summarizes chat and embedding models without pretending custom is an api key provider", () => {
  const provider = {
    id: "custom",
    name: "Custom",
    connected: true,
    from_env: false,
    key_hint: null,
    model_count: 2,
    models: [
      { id: "local/a", base_url: "http://localhost:11434/v1", context_window: 8192 },
      { id: "local/b", base_url: "http://localhost:11434/v1", context_window: 8192 },
    ],
    embedding_models: [],
  } as const;

  expect(providerActionLabel(provider)).toBe("Manage");
  expect(providerModelCountLabel(provider)).toBe("2 models");
});

test("summarizes chat model readiness from the active model provider", () => {
  const summary = providerReadinessSummary(
    [
      {
        id: "openai",
        name: "OpenAI",
        connected: true,
        from_env: false,
        auth_type: "api_key",
        models: ["gpt-5.5"],
        embedding_models: ["text-embedding-3-small"],
      },
      {
        id: "anthropic",
        name: "Anthropic",
        connected: false,
        from_env: false,
        auth_type: "api_key",
        models: ["claude-sonnet-4-6"],
        embedding_models: [],
      },
    ],
    "gpt-5.5",
  );

  expect(summary.ready).toBe(true);
  expect(summary.label).toBe("Chat model ready");
  expect(summary.detail).toBe("OpenAI provides gpt-5.5");
  expect(summary.currentProviderName).toBe("OpenAI");
  expect(summary.connectedProviderCount).toBe(1);
  expect(summary.availableModelCount).toBe(2);
});
