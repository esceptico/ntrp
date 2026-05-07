export type ProviderAuthType = "api_key" | "oauth";

export interface ProviderConnectionLike {
  id: string;
  name: string;
  connected: boolean;
  from_env: boolean;
  auth_type?: ProviderAuthType;
  key_hint?: string | null;
  model_count?: number;
  models: readonly (string | { id: string })[];
  embedding_models: readonly string[];
}

export function providerConnectionLabel(provider: ProviderConnectionLike): string {
  if (!provider.connected) return "Not connected";
  if (provider.from_env) return "Connected via env";
  if (provider.key_hint) return provider.key_hint;
  return "Connected";
}

export function providerActionLabel(provider: ProviderConnectionLike): string {
  if (provider.id === "custom") return "Manage";
  if (provider.connected && provider.from_env) return "Env-managed";
  if (provider.connected) return "Disconnect";
  return provider.auth_type === "oauth" ? "Sign in" : "Connect";
}

export function providerModelCountLabel(provider: ProviderConnectionLike): string {
  const chatCount = provider.model_count ?? provider.models.length;
  const embeddingCount = provider.embedding_models.length;
  const chatWord = chatCount === 1 ? "model" : "models";
  if (embeddingCount === 0) return `${chatCount} ${chatWord}`;
  const embeddingWord = embeddingCount === 1 ? "embedding" : "embeddings";
  return `${chatCount} ${chatWord} · ${embeddingCount} ${embeddingWord}`;
}
