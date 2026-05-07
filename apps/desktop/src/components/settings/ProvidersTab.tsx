import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import clsx from "clsx";
import { CheckCircle2, ExternalLink, KeyRound, Loader2, Plus, RefreshCw, Trash2 } from "lucide-react";
import {
  createCustomModelApi,
  connectModelProviderApi,
  deleteCustomModelApi,
  disconnectModelProviderApi,
  getOpenAICodexOAuthStatusApi,
  listModelProvidersApi,
  type CustomModelSummary,
  startOpenAICodexOAuthApi,
  type ModelProvider,
  type OpenAICodexOAuthStatus,
} from "../../api";
import { fetchServerConfig, updateServerConfig } from "../../actions";
import { useStore } from "../../store";
import {
  providerActionLabel,
  providerConnectionLabel,
  providerModelCountLabel,
} from "../../lib/providerConnection";
import {
  canSaveCustomModelDraft,
  defaultCustomModelDraft,
  type CustomModelDraft,
} from "../../lib/customModelDraft";
import {
  settingsErrorMessage,
  settingsErrorTitle,
  shouldShowLoadedSettingsContent,
} from "../../lib/settingsLoadState";
import { SettingsConnectionHint, SettingsInlineError } from "./SettingsNotice";

const PRIMARY_PROVIDERS = ["openai-codex", "openai", "anthropic", "google", "openrouter"];

function modelIds(provider: ModelProvider): string[] {
  return provider.models.map((model) => (typeof model === "string" ? model : model.id));
}

function customModels(provider: ModelProvider): CustomModelSummary[] {
  return provider.models.filter((model): model is CustomModelSummary => typeof model !== "string");
}

function providerDescription(id: string): string {
  switch (id) {
    case "openai-codex":
      return "Use your OpenAI account login for Codex-backed models.";
    case "openai":
      return "Use OpenAI API keys for GPT models and embeddings.";
    case "anthropic":
      return "Use Anthropic API keys for Claude models.";
    case "google":
      return "Use Gemini API keys for Gemini chat and embeddings.";
    case "openrouter":
      return "Use OpenRouter API keys for routed third-party models.";
    case "custom":
      return "OpenAI-compatible local or hosted models.";
    default:
      return "Connect this model provider.";
  }
}

function statusTone(provider: ModelProvider): string {
  if (provider.connected) return "bg-ok-soft text-ok";
  return "bg-surface-soft text-faint";
}

export function ProvidersTab() {
  const config = useStore((s) => s.config);
  const serverConfig = useStore((s) => s.serverConfig);
  const [providers, setProviders] = useState<ModelProvider[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loadedOnce, setLoadedOnce] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [codexStatus, setCodexStatus] = useState<OpenAICodexOAuthStatus | null>(null);
  const [customOpen, setCustomOpen] = useState(false);
  const [customDraft, setCustomDraft] = useState<CustomModelDraft>(() => defaultCustomModelDraft());

  const sortedProviders = useMemo(() => {
    const rank = new Map(PRIMARY_PROVIDERS.map((id, index) => [id, index]));
    return providers
      .slice()
      .sort((a, b) => (rank.get(a.id) ?? 99) - (rank.get(b.id) ?? 99));
  }, [providers]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const next = await listModelProvidersApi(config);
      setProviders(next);
      setLoadedOnce(true);
      const codex = next.find((provider) => provider.id === "openai-codex");
      if (codex?.connected) {
        setCodexStatus({ connected: true, status: "connected" });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [config]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (codexStatus?.status !== "pending") return;
    const interval = window.setInterval(async () => {
      try {
        const next = await getOpenAICodexOAuthStatusApi(config);
        setCodexStatus(next);
        if (next.connected) {
          await refresh();
          await fetchServerConfig();
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    }, 1500);
    return () => window.clearInterval(interval);
  }, [codexStatus?.status, config, refresh]);

  async function connect(provider: ModelProvider) {
    if (!apiKey.trim()) return;
    setPendingId(provider.id);
    setError(null);
    try {
      await connectModelProviderApi(config, provider.id, apiKey.trim());
      setEditingId(null);
      setApiKey("");
      await refresh();
      await fetchServerConfig();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPendingId(null);
    }
  }

  async function disconnect(provider: ModelProvider) {
    setPendingId(provider.id);
    setError(null);
    try {
      await disconnectModelProviderApi(config, provider.id);
      await refresh();
      await fetchServerConfig();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPendingId(null);
    }
  }

  async function startCodexSignIn() {
    setPendingId("openai-codex");
    setError(null);
    try {
      const status = await startOpenAICodexOAuthApi(config);
      setCodexStatus({ connected: false, status: status.status, url: status.url, opened: status.opened });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPendingId(null);
    }
  }

  async function useForAgent(provider: ModelProvider) {
    const [first] = modelIds(provider);
    if (!first || serverConfig?.chat_model === first) return;
    await useModelForAgent(first, provider.id);
  }

  async function useModelForAgent(modelId: string, pendingKey: string) {
    if (!modelId || serverConfig?.chat_model === modelId) return;
    setPendingId(`${pendingKey}:agent`);
    setError(null);
    try {
      await updateServerConfig({ chat_model: modelId });
      await fetchServerConfig();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPendingId(null);
    }
  }

  async function createCustomModel() {
    if (!canSaveCustomModelDraft(customDraft)) return;
    setPendingId("custom:create");
    setError(null);
    try {
      await createCustomModelApi(config, {
        model_id: customDraft.model_id.trim(),
        base_url: customDraft.base_url.trim(),
        context_window: customDraft.context_window,
        max_output_tokens: customDraft.max_output_tokens,
        api_key: customDraft.api_key.trim() || null,
      });
      setCustomDraft(defaultCustomModelDraft());
      await refresh();
      await fetchServerConfig();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPendingId(null);
    }
  }

  async function deleteCustomModel(modelId: string) {
    setPendingId(`custom:delete:${modelId}`);
    setError(null);
    try {
      await deleteCustomModelApi(config, modelId);
      await refresh();
      await fetchServerConfig();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPendingId(null);
    }
  }

  function updateCustomDraft(patch: Partial<CustomModelDraft>) {
    setCustomDraft((prev) => ({ ...prev, ...patch }));
  }

  const hasLoadedData = loadedOnce || providers.length > 0;
  const showContent = shouldShowLoadedSettingsContent({ loading, error, hasData: hasLoadedData });

  return (
    <div className="grid gap-4">
      <div className="flex items-start justify-between gap-3">
        <p className="m-0 text-[12.5px] text-muted leading-[1.45] max-w-[520px]">
          Connect model providers here. Server connection and tool integrations stay separate.
        </p>
        <button
          type="button"
          onClick={() => void refresh()}
          disabled={loading}
          className="inline-flex items-center gap-1.5 h-8 px-2.5 rounded-md border border-line bg-surface text-[12px] text-ink-soft hover:border-line-strong transition-colors disabled:opacity-50"
        >
          <RefreshCw size={12} strokeWidth={1.8} className={clsx(loading && "animate-spin")} />
          Refresh
        </button>
      </div>

      {error && (
        <SettingsInlineError
          title={settingsErrorTitle("providers", hasLoadedData)}
          message={settingsErrorMessage(error)}
        />
      )}

      <div className="grid gap-2">
        {loading && providers.length === 0 ? (
          <div className="text-[12.5px] text-faint">Loading providers…</div>
        ) : !showContent ? (
          <SettingsConnectionHint />
        ) : (
          sortedProviders.map((provider) => (
            <ProviderRow
              key={provider.id}
              provider={provider}
              editing={editingId === provider.id}
              apiKey={editingId === provider.id ? apiKey : ""}
              pending={pendingId === provider.id}
              agentPending={pendingId === `${provider.id}:agent`}
              currentAgentModel={serverConfig?.chat_model ?? null}
              codexStatus={provider.id === "openai-codex" ? codexStatus : null}
              customOpen={provider.id === "custom" ? customOpen : false}
              onToggleCustom={() => setCustomOpen((value) => !value)}
              onEdit={() => {
                setEditingId(provider.id);
                setApiKey("");
              }}
              onCancel={() => {
                setEditingId(null);
                setApiKey("");
              }}
              onKeyChange={setApiKey}
              onConnect={() => void connect(provider)}
              onDisconnect={() => void disconnect(provider)}
              onCodexSignIn={() => void startCodexSignIn()}
              onUseForAgent={() => void useForAgent(provider)}
            >
              {provider.id === "custom" && customOpen && (
                <CustomModelsPanel
                  provider={provider}
                  draft={customDraft}
                  pendingId={pendingId}
                  currentAgentModel={serverConfig?.chat_model ?? null}
                  onDraftChange={updateCustomDraft}
                  onCreate={() => void createCustomModel()}
                  onDelete={(modelId) => void deleteCustomModel(modelId)}
                  onUseForAgent={(modelId) => void useModelForAgent(modelId, `custom:${modelId}`)}
                />
              )}
            </ProviderRow>
          ))
        )}
      </div>
    </div>
  );
}

function ProviderRow({
  provider,
  editing,
  apiKey,
  pending,
  agentPending,
  currentAgentModel,
  codexStatus,
  customOpen,
  onEdit,
  onCancel,
  onKeyChange,
  onConnect,
  onDisconnect,
  onCodexSignIn,
  onUseForAgent,
  onToggleCustom,
  children,
}: {
  provider: ModelProvider;
  editing: boolean;
  apiKey: string;
  pending: boolean;
  agentPending: boolean;
  currentAgentModel: string | null;
  codexStatus: OpenAICodexOAuthStatus | null;
  customOpen: boolean;
  onEdit: () => void;
  onCancel: () => void;
  onKeyChange: (value: string) => void;
  onConnect: () => void;
  onDisconnect: () => void;
  onCodexSignIn: () => void;
  onUseForAgent: () => void;
  onToggleCustom: () => void;
  children?: ReactNode;
}) {
  const ids = modelIds(provider);
  const isCustom = provider.id === "custom";
  const canUseForAgent = !isCustom && provider.connected && ids.length > 0 && !ids.includes(currentAgentModel ?? "");
  const isOauth = provider.auth_type === "oauth";
  const actionLabel = isCustom ? (customOpen ? "Done" : "Manage") : pending ? "Working…" : providerActionLabel(provider);
  const readOnlyPrimary = provider.connected && provider.from_env;

  function primaryAction() {
    if (isCustom) {
      onToggleCustom();
      return;
    }
    if (isOauth) {
      if (provider.connected) onDisconnect();
      else onCodexSignIn();
      return;
    }
    if (provider.connected) onDisconnect();
    else onEdit();
  }

  return (
    <div className="rounded-[12px] border border-line-soft bg-surface overflow-hidden">
      <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-3 px-3.5 py-3">
        <div className="min-w-0 grid gap-1">
          <div className="flex items-center gap-2 min-w-0">
            <ProviderIcon connected={provider.connected} />
            <div className="text-[13px] font-medium text-ink truncate">{provider.name}</div>
            <span className={clsx("px-1.5 py-0.5 rounded-full text-[10.5px] font-medium", statusTone(provider))}>
              {providerConnectionLabel(provider)}
            </span>
          </div>
          <div className="text-[11.5px] text-faint leading-[1.4]">{providerDescription(provider.id)}</div>
          <div className="text-[11.5px] text-muted font-mono truncate">
            {providerModelCountLabel(provider)}
          </div>
        </div>

        <div className="flex items-center gap-2">
          {canUseForAgent && (
            <button
              type="button"
              onClick={onUseForAgent}
              disabled={agentPending}
              className="h-8 px-2.5 rounded-md border border-line bg-surface text-[12px] text-ink-soft hover:border-line-strong transition-colors disabled:opacity-50"
            >
              {agentPending ? "Saving…" : "Use for agent"}
            </button>
          )}
          {readOnlyPrimary ? (
            <span className="inline-flex items-center h-8 px-3 rounded-md border border-line-soft bg-surface-soft text-[12px] font-medium text-muted">
              {isCustom ? "Configured separately" : actionLabel}
            </span>
          ) : (
            <button
              type="button"
              onClick={primaryAction}
              disabled={pending}
              className={clsx(
                "h-8 px-3 rounded-md text-[12px] font-medium transition-colors disabled:opacity-50",
                provider.connected
                  ? "border border-line bg-surface text-ink-soft hover:border-line-strong"
                  : "bg-ink text-on-ink hover:opacity-90",
              )}
            >
              {actionLabel}
            </button>
          )}
        </div>
      </div>

      {editing && !provider.connected && !isOauth && !isCustom && (
        <div className="grid grid-cols-[minmax(0,1fr)_auto_auto] gap-2 px-3.5 py-3 border-t border-line-soft bg-surface-soft/35">
          <input
            type="password"
            value={apiKey}
            onChange={(event) => onKeyChange(event.target.value)}
            placeholder="API key"
            autoFocus
            className="h-9 px-3 rounded-[9px] border border-line bg-surface text-[13px] text-ink outline-none hover:border-line-strong focus:border-accent focus:shadow-[0_0_0_3px_var(--color-accent-soft)] transition-[border-color,box-shadow]"
          />
          <button
            type="button"
            onClick={onConnect}
            disabled={!apiKey.trim() || pending}
            className="h-9 px-3 rounded-[9px] bg-ink text-on-ink text-[12px] font-medium hover:opacity-90 disabled:opacity-40 transition-opacity"
          >
            Connect
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="h-9 px-3 rounded-[9px] border border-line bg-surface text-[12px] text-muted hover:text-ink hover:border-line-strong transition-colors"
          >
            Cancel
          </button>
        </div>
      )}

      {codexStatus?.status === "pending" && (
        <div className="flex items-center gap-2 px-3.5 py-2.5 border-t border-line-soft bg-surface-soft/35 text-[12px] text-muted">
          <Loader2 size={13} strokeWidth={1.8} className="animate-spin" />
          <span>Waiting for browser sign-in…</span>
          {codexStatus.url && (
            <a
              href={codexStatus.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-info hover:underline underline-offset-2"
            >
              Open URL <ExternalLink size={11} strokeWidth={1.8} />
            </a>
          )}
        </div>
      )}

      {codexStatus?.error && (
        <div className="px-3.5 py-2.5 border-t border-line-soft bg-bad-soft text-[12px] text-bad">
          {codexStatus.error}
        </div>
      )}

      {children}
    </div>
  );
}

function CustomModelsPanel({
  provider,
  draft,
  pendingId,
  currentAgentModel,
  onDraftChange,
  onCreate,
  onDelete,
  onUseForAgent,
}: {
  provider: ModelProvider;
  draft: CustomModelDraft;
  pendingId: string | null;
  currentAgentModel: string | null;
  onDraftChange: (patch: Partial<CustomModelDraft>) => void;
  onCreate: () => void;
  onDelete: (modelId: string) => void;
  onUseForAgent: (modelId: string) => void;
}) {
  const models = customModels(provider);
  const creating = pendingId === "custom:create";

  return (
    <div className="grid gap-3 px-3.5 py-3 border-t border-line-soft bg-surface-soft/35">
      <div className="grid gap-1.5">
        {models.length === 0 ? (
          <div className="text-[12px] text-faint">No custom models configured.</div>
        ) : (
          models.map((model) => {
            const deleting = pendingId === `custom:delete:${model.id}`;
            const agentPending = pendingId === `custom:${model.id}:agent`;
            const active = currentAgentModel === model.id;
            return (
              <div
                key={model.id}
                className="grid grid-cols-[minmax(0,1fr)_auto] gap-2 items-center rounded-[9px] border border-line-soft bg-surface px-2.5 py-2"
              >
                <div className="min-w-0">
                  <div className="text-[12.5px] font-medium text-ink-soft truncate">{model.id}</div>
                  <div className="text-[11px] text-faint truncate">
                    {model.base_url || "default base URL"} · {model.context_window.toLocaleString()} ctx
                  </div>
                </div>
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => onUseForAgent(model.id)}
                    disabled={active || agentPending}
                    className="h-7 px-2 rounded-md border border-line bg-surface text-[11.5px] text-ink-soft hover:border-line-strong transition-colors disabled:opacity-45"
                  >
                    {active ? "Active" : agentPending ? "Saving…" : "Use"}
                  </button>
                  <button
                    type="button"
                    aria-label={`Delete ${model.id}`}
                    onClick={() => onDelete(model.id)}
                    disabled={deleting}
                    className="grid place-items-center w-7 h-7 rounded-md text-muted hover:bg-surface-soft hover:text-bad transition-colors disabled:opacity-50"
                  >
                    {deleting ? (
                      <Loader2 size={13} strokeWidth={1.8} className="animate-spin" />
                    ) : (
                      <Trash2 size={13} strokeWidth={1.8} />
                    )}
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>

      <div className="grid gap-2">
        <div className="grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-2">
          <input
            value={draft.model_id}
            onChange={(event) => onDraftChange({ model_id: event.target.value })}
            placeholder="model id"
            className="h-9 px-3 rounded-[9px] border border-line bg-surface text-[13px] text-ink outline-none hover:border-line-strong focus:border-accent focus:shadow-[0_0_0_3px_var(--color-accent-soft)] transition-[border-color,box-shadow]"
          />
          <input
            value={draft.base_url}
            onChange={(event) => onDraftChange({ base_url: event.target.value })}
            placeholder="base URL"
            className="h-9 px-3 rounded-[9px] border border-line bg-surface text-[13px] text-ink outline-none hover:border-line-strong focus:border-accent focus:shadow-[0_0_0_3px_var(--color-accent-soft)] transition-[border-color,box-shadow]"
          />
        </div>
        <div className="grid grid-cols-[repeat(auto-fit,minmax(130px,1fr))] gap-2">
          <input
            type="number"
            min={1}
            value={draft.context_window}
            onChange={(event) => onDraftChange({ context_window: Number(event.target.value) })}
            aria-label="Context window"
            className="h-9 px-3 rounded-[9px] border border-line bg-surface text-[13px] text-ink outline-none hover:border-line-strong focus:border-accent focus:shadow-[0_0_0_3px_var(--color-accent-soft)] transition-[border-color,box-shadow]"
          />
          <input
            type="number"
            min={1}
            value={draft.max_output_tokens}
            onChange={(event) => onDraftChange({ max_output_tokens: Number(event.target.value) })}
            aria-label="Max output tokens"
            className="h-9 px-3 rounded-[9px] border border-line bg-surface text-[13px] text-ink outline-none hover:border-line-strong focus:border-accent focus:shadow-[0_0_0_3px_var(--color-accent-soft)] transition-[border-color,box-shadow]"
          />
          <input
            type="password"
            value={draft.api_key}
            onChange={(event) => onDraftChange({ api_key: event.target.value })}
            placeholder="API key (optional)"
            className="h-9 px-3 rounded-[9px] border border-line bg-surface text-[13px] text-ink outline-none hover:border-line-strong focus:border-accent focus:shadow-[0_0_0_3px_var(--color-accent-soft)] transition-[border-color,box-shadow]"
          />
          <button
            type="button"
            onClick={onCreate}
            disabled={!canSaveCustomModelDraft(draft) || creating}
            className="inline-flex items-center justify-center gap-1.5 h-9 px-3 rounded-[9px] bg-ink text-on-ink text-[12px] font-medium hover:opacity-90 disabled:opacity-40 transition-opacity"
          >
            {creating ? <Loader2 size={13} strokeWidth={1.8} className="animate-spin" /> : <Plus size={13} strokeWidth={2} />}
            Add
          </button>
        </div>
      </div>
    </div>
  );
}

function ProviderIcon({ connected }: { connected: boolean }) {
  return connected ? (
    <CheckCircle2 size={14} strokeWidth={2} className="text-ok shrink-0" />
  ) : (
    <KeyRound size={14} strokeWidth={1.8} className="text-faint shrink-0" />
  );
}
