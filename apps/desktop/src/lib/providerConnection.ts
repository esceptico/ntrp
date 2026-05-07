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

export function providerConnectionPill(provider: ProviderConnectionLike): string | null {
  if (!provider.connected) return null;
  return providerConnectionLabel(provider);
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

export interface ProviderReadinessSummary {
  ready: boolean;
  label: string;
  detail: string;
  currentModel: string | null;
  currentProviderName: string | null;
  connectedProviderCount: number;
  availableModelCount: number;
}

export function providerReadinessSummary(
  providers: readonly ProviderConnectionLike[],
  currentModel: string | null,
): ProviderReadinessSummary {
  const connected = providers.filter((provider) => provider.connected);
  const currentProvider = currentModel
    ? connected.find((provider) =>
        provider.models.some((model) => (typeof model === "string" ? model : model.id) === currentModel),
      )
    : undefined;
  const availableModelCount = providers.reduce(
    (count, provider) => count + (provider.model_count ?? provider.models.length),
    0,
  );

  if (currentProvider && currentModel) {
    return {
      ready: true,
      label: "Agent ready",
      detail: `${currentProvider.name} powers ${currentModel}`,
      currentModel,
      currentProviderName: currentProvider.name,
      connectedProviderCount: connected.length,
      availableModelCount,
    };
  }

  if (connected.length > 0) {
    return {
      ready: false,
      label: "Choose an agent model",
      detail: `${connected.length} ${connected.length === 1 ? "provider is" : "providers are"} connected`,
      currentModel,
      currentProviderName: null,
      connectedProviderCount: connected.length,
      availableModelCount,
    };
  }

  return {
    ready: false,
    label: "Connect a model provider",
    detail: "The agent needs at least one chat model provider",
    currentModel,
    currentProviderName: null,
    connectedProviderCount: 0,
    availableModelCount,
  };
}
