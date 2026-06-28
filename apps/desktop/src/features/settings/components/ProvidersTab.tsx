import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import clsx from "clsx";
import { CheckCircle2, ExternalLink, KeyRound, Loader2, Plus, RefreshCw } from "lucide-react";
import { createCustomModelApi, connectModelProviderApi, deleteCustomModelApi, disconnectModelProviderApi, getOpenAICodexOAuthStatusApi, listModelProvidersApi, type CustomModelSummary, startOpenAICodexOAuthApi, type ModelProvider, type OpenAICodexOAuthStatus } from "@/api/settings";
import { fetchServerConfig } from "@/actions/server";
import { useStore } from "@/stores";
import { ReadinessCard } from "@/features/settings/components/ReadinessCard";
import { SectionHeader } from "@/components/ui/SectionHeader";
import {
  providerActionLabel,
  providerConnectionPill,
  providerModelCountLabel,
  providerReadinessSummary,
} from "@/features/settings/lib/providerConnection";
import {
  canSaveCustomModelDraft,
  defaultCustomModelDraft,
  type CustomModelDraft,
} from "@/features/settings/lib/customModelDraft";
import {
  settingsErrorMessage,
  settingsErrorTitle,
  shouldShowLoadedSettingsContent,
} from "@/features/settings/lib/settingsLoadState";
import { SettingsConnectionHint, SettingsInlineError } from "@/features/settings/components/SettingsNotice";
import { DISSOLVE_OUT, EASE_OUT, MOTION, RISE_IN, RISE_SETTLED } from "@/lib/tokens/motion";
import { ICON } from "@/lib/icons";
import { BlurSwap } from "@/components/ui/BlurSwap";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ConfirmDeleteButton } from "@/components/ui/ConfirmDeleteButton";

const PRIMARY_PROVIDERS = ["openai-codex", "openai", "anthropic", "google", "openrouter"];

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
  const connectedProviders = useMemo(
    () => sortedProviders.filter((provider) => provider.connected),
    [sortedProviders],
  );
  const setupProviders = useMemo(
    () => sortedProviders.filter((provider) => !provider.connected),
    [sortedProviders],
  );
  const readiness = useMemo(
    () => providerReadinessSummary(sortedProviders, serverConfig?.chat_model ?? null),
    [serverConfig?.chat_model, sortedProviders],
  );

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

  function renderProvider(provider: ModelProvider) {
    return (
      <ProviderRow
        key={provider.id}
        provider={provider}
        editing={editingId === provider.id}
        apiKey={editingId === provider.id ? apiKey : ""}
        pending={pendingId === provider.id}
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
      >
        {provider.id === "custom" && (
          <AnimatePresence initial={false}>
            {customOpen && (
              <motion.div
                key="custom-models"
                initial={{ ...RISE_IN, y: -4 }}
                animate={RISE_SETTLED}
                exit={{ ...DISSOLVE_OUT, transition: { duration: MOTION.fast, ease: EASE_OUT } }}
                transition={{ duration: MOTION.row, ease: EASE_OUT }}
              >
                <CustomModelsPanel
                  provider={provider}
                  draft={customDraft}
                  pendingId={pendingId}
                  onDraftChange={updateCustomDraft}
                  onCreate={() => void createCustomModel()}
                  onDelete={(modelId) => void deleteCustomModel(modelId)}
                />
              </motion.div>
            )}
          </AnimatePresence>
        )}
      </ProviderRow>
    );
  }

  return (
    <div className="grid gap-4">
      <div className="flex items-start justify-between gap-3">
        <p className="m-0 text-sm text-muted leading-[1.45] max-w-[520px]">
          Connect model providers here. Server connection and tool integrations stay separate.
        </p>
        <Button variant="secondary" onClick={() => void refresh()} disabled={loading}>
          <RefreshCw size={ICON.SM} strokeWidth={2} className={clsx(loading && "animate-spin")} />
          Refresh
        </Button>
      </div>

      {error && (
        <SettingsInlineError
          title={settingsErrorTitle("providers", hasLoadedData)}
          message={settingsErrorMessage(error)}
        />
      )}

      <div className="grid gap-3">
        {loading && providers.length === 0 ? (
          <div className="text-sm text-muted">Loading providers…</div>
        ) : !showContent ? (
          <SettingsConnectionHint />
        ) : (
          <>
            <ReadinessCard
              tone={readiness.ready ? "ok" : "warn"}
              label={readiness.label}
              detail={readiness.detail}
              footnote={`${readiness.connectedProviderCount} connected · ${readiness.availableModelCount} available models`}
            />
            <ProviderSection
              title="Ready providers"
              detail={`${connectedProviders.length} connected`}
              empty="No model providers are connected yet."
            >
              {connectedProviders.map(renderProvider)}
            </ProviderSection>
            <ProviderSection
              title="Set up more"
              detail={`${setupProviders.length} available`}
              empty="All configured providers are ready."
            >
              {setupProviders.map(renderProvider)}
            </ProviderSection>
          </>
        )}
      </div>
    </div>
  );
}

function ProviderSection({
  title,
  detail,
  empty,
  children,
}: {
  title: string;
  detail: string;
  empty: string;
  children: ReactNode;
}) {
  const childCount = Array.isArray(children) ? children.length : children ? 1 : 0;

  return (
    <section className="grid gap-2">
      <SectionHeader label={title} detail={detail} className="px-0.5" />
      {childCount > 0 ? (
        <div className="grid gap-2">{children}</div>
      ) : (
        <div className="rounded-[10px] border border-line-soft bg-surface px-3 py-2 text-sm text-muted">
          {empty}
        </div>
      )}
    </section>
  );
}

function ProviderRow({
  provider,
  editing,
  apiKey,
  pending,
  codexStatus,
  customOpen,
  onEdit,
  onCancel,
  onKeyChange,
  onConnect,
  onDisconnect,
  onCodexSignIn,
  onToggleCustom,
  children,
}: {
  provider: ModelProvider;
  editing: boolean;
  apiKey: string;
  pending: boolean;
  codexStatus: OpenAICodexOAuthStatus | null;
  customOpen: boolean;
  onEdit: () => void;
  onCancel: () => void;
  onKeyChange: (value: string) => void;
  onConnect: () => void;
  onDisconnect: () => void;
  onCodexSignIn: () => void;
  onToggleCustom: () => void;
  children?: ReactNode;
}) {
  const isCustom = provider.id === "custom";
  const isOauth = provider.auth_type === "oauth";
  const actionLabel = isCustom ? (customOpen ? "Done" : "Manage") : pending ? "Working…" : providerActionLabel(provider);
  const readOnlyPrimary = provider.connected && provider.from_env;
  const connectionPill = providerConnectionPill(provider);

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
      <div className="flex flex-wrap items-start gap-3 px-3.5 py-2.5">
        <div className="min-w-[150px] flex-1 grid gap-1">
          <div className="flex items-center gap-2 min-w-0">
            <ProviderIcon connected={provider.connected} />
            <div className="text-base font-medium text-ink truncate">{provider.name}</div>
          </div>
          <div className="text-xs text-muted font-mono truncate">
            {provider.connected
              ? `${providerModelCountLabel(provider)}${connectionPill ? ` · ${connectionPill}` : ""}`
              : providerDescription(provider.id)}
          </div>
          {!provider.connected && (
            <div className="text-xs text-muted font-mono truncate">
              {providerModelCountLabel(provider)}
            </div>
          )}
        </div>

        <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
          {readOnlyPrimary ? (
            <span className="inline-flex items-center h-8 px-3 rounded-md border border-line-soft bg-surface-soft text-sm font-medium text-muted">
              {isCustom ? "Configured separately" : actionLabel}
            </span>
          ) : (
            <Button
              variant={provider.connected ? "secondary" : "primary"}
              onClick={primaryAction}
              disabled={pending}
            >
              <BlurSwap swapKey={actionLabel} blur={2}>
                {actionLabel}
              </BlurSwap>
            </Button>
          )}
        </div>
      </div>

      <AnimatePresence initial={false}>
        {editing && !provider.connected && !isOauth && !isCustom && (
          <motion.div
            key="key-editor"
            initial={{ ...RISE_IN, y: -4 }}
            animate={RISE_SETTLED}
            exit={{ ...DISSOLVE_OUT, transition: { duration: MOTION.fast, ease: EASE_OUT } }}
            transition={{ duration: MOTION.row, ease: EASE_OUT }}
            className="grid grid-cols-[minmax(0,1fr)_auto_auto] gap-2 px-3.5 py-3 bg-surface-soft/35"
          >
            <Input
              type="password"
              value={apiKey}
              onChange={(event) => onKeyChange(event.target.value)}
              placeholder="API key"
              aria-label="API key"
              autoFocus
              spellCheck={false}
              autoComplete="off"
            />
            <Button onClick={onConnect} disabled={!apiKey.trim() || pending}>
              {pending && <Loader2 size={ICON.MD} strokeWidth={2} className="animate-spin" />}
              Connect
            </Button>
            <Button variant="secondary" onClick={onCancel}>
              Cancel
            </Button>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence initial={false}>
        {codexStatus?.status === "pending" && (
          <motion.div
            key="codex-pending"
            initial={{ ...RISE_IN, y: -4 }}
            animate={RISE_SETTLED}
            exit={{ ...DISSOLVE_OUT, transition: { duration: MOTION.fast, ease: EASE_OUT } }}
            transition={{ duration: MOTION.row, ease: EASE_OUT }}
            className="flex items-center gap-2 px-3.5 py-2.5 bg-surface-soft/35 text-sm text-muted"
          >
            <Loader2 size={ICON.MD} strokeWidth={2} className="animate-spin" />
            <span>Waiting for browser sign-in…</span>
            {codexStatus.url && (
              <a
                href={codexStatus.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-info hover:underline underline-offset-2"
              >
                Open URL <ExternalLink size={ICON.XS} strokeWidth={2} />
              </a>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence initial={false}>
        {codexStatus?.error && (
          <motion.div
            key="codex-error"
            initial={{ ...RISE_IN, y: -4 }}
            animate={RISE_SETTLED}
            exit={{ ...DISSOLVE_OUT, transition: { duration: MOTION.fast, ease: EASE_OUT } }}
            transition={{ duration: MOTION.row, ease: EASE_OUT }}
            className="px-3.5 py-2.5 bg-bad-soft text-sm text-bad"
          >
            {codexStatus.error}
          </motion.div>
        )}
      </AnimatePresence>

      {children}
    </div>
  );
}

function CustomModelsPanel({
  provider,
  draft,
  pendingId,
  onDraftChange,
  onCreate,
  onDelete,
}: {
  provider: ModelProvider;
  draft: CustomModelDraft;
  pendingId: string | null;
  onDraftChange: (patch: Partial<CustomModelDraft>) => void;
  onCreate: () => void;
  onDelete: (modelId: string) => void;
}) {
  const models = customModels(provider);
  const creating = pendingId === "custom:create";

  return (
    <div className="grid gap-3 px-3.5 py-3 bg-surface-soft/35">
      <div className="grid gap-1.5">
        {models.length === 0 ? (
          <div className="text-sm text-muted">No custom models configured.</div>
        ) : (
          models.map((model) => {
            const deleting = pendingId === `custom:delete:${model.id}`;
            return (
              <div
                key={model.id}
                className="grid grid-cols-[minmax(0,1fr)_auto] gap-2 items-center rounded-[9px] border border-line-soft bg-surface px-2.5 py-2"
              >
                <div className="min-w-0">
                  <div className="text-sm font-medium text-ink-soft truncate">{model.id}</div>
                  <div className="text-xs text-muted truncate">
                    {model.base_url || "default base URL"} · {model.context_window.toLocaleString()} ctx
                  </div>
                </div>
                <div className="flex items-center gap-1.5">
                  <ConfirmDeleteButton
                    size="md"
                    label={`Delete ${model.id}`}
                    busy={deleting}
                    onConfirm={() => onDelete(model.id)}
                  />
                </div>
              </div>
            );
          })
        )}
      </div>

      <div className="grid gap-2">
        <div className="grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-2">
          <Input
            value={draft.model_id}
            onChange={(event) => onDraftChange({ model_id: event.target.value })}
            placeholder="model id"
            aria-label="Model ID"
            spellCheck={false}
          />
          <Input
            value={draft.base_url}
            onChange={(event) => onDraftChange({ base_url: event.target.value })}
            placeholder="base URL"
            aria-label="Base URL"
            spellCheck={false}
            autoComplete="off"
          />
        </div>
        <div className="grid grid-cols-[repeat(auto-fit,minmax(130px,1fr))] gap-2">
          <Input
            type="number"
            min={1}
            value={draft.context_window}
            onChange={(event) => onDraftChange({ context_window: Number(event.target.value) })}
            aria-label="Context window"
          />
          <Input
            type="number"
            min={1}
            value={draft.max_output_tokens}
            onChange={(event) => onDraftChange({ max_output_tokens: Number(event.target.value) })}
            aria-label="Max output tokens"
          />
          <Input
            type="password"
            value={draft.api_key}
            onChange={(event) => onDraftChange({ api_key: event.target.value })}
            placeholder="API key (optional)"
            spellCheck={false}
            autoComplete="off"
          />
          <Button onClick={onCreate} disabled={!canSaveCustomModelDraft(draft) || creating}>
            <BlurSwap swapKey={creating ? "loading" : "add"} blur={3}>
              {creating ? (
                <Loader2 size={ICON.MD} strokeWidth={2} className="animate-spin" />
              ) : (
                <Plus size={ICON.MD} strokeWidth={2} />
              )}
            </BlurSwap>
            Add
          </Button>
        </div>
      </div>
    </div>
  );
}

function ProviderIcon({ connected }: { connected: boolean }) {
  return connected ? (
    <CheckCircle2 size={ICON.MD} strokeWidth={2} className="text-ok shrink-0" />
  ) : (
    <KeyRound size={ICON.MD} strokeWidth={2} className="text-faint shrink-0" />
  );
}
