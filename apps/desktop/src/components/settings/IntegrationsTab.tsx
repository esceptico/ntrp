import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import clsx from "clsx";
import {
  CalendarDays,
  CheckCircle2,
  KeyRound,
  Mail,
  MessageCircle,
  RefreshCw,
} from "lucide-react";
import {
  addGmailAccountApi,
  connectServiceApi,
  disconnectServiceApi,
  listGmailAccountsApi,
  listServicesApi,
  removeGmailAccountApi,
  type GmailAccount,
  type ServiceConnection,
} from "../../api";
import { fetchServerConfig, updateServerConfig } from "../../actions";
import { useStore } from "../../store";
import { ReadinessCard } from "../ReadinessCard";
import { SectionHeader } from "../SectionHeader";
import {
  googleConnectionSummary,
  type GoogleConnectionSummary,
  serviceActionLabel,
  serviceConnectionPill,
} from "../../lib/integrationConnection";
import {
  settingsErrorMessage,
  settingsErrorTitle,
  shouldShowLoadedSettingsContent,
} from "../../lib/settingsLoadState";
import { SettingsConnectionHint, SettingsInlineError } from "./SettingsNotice";
import { DISSOLVE_OUT, EASE_OUT, MOTION, RISE_IN, RISE_SETTLED } from "../../lib/tokens/motion";
import { ICON } from "../../lib/icons";
import { BlurSwap } from "../BlurSwap";
import { ConfirmDeleteButton } from "../ui/ConfirmDeleteButton";
import { SetupAssistant, type SetupAssistantKind } from "./setup/SetupAssistant";

export function IntegrationsTab() {
  const config = useStore((s) => s.config);
  const serverConfig = useStore((s) => s.serverConfig);
  const [services, setServices] = useState<ServiceConnection[]>([]);
  const [gmailAccounts, setGmailAccounts] = useState<GmailAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loadedOnce, setLoadedOnce] = useState(false);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [serviceKey, setServiceKey] = useState("");
  const [assistant, setAssistant] = useState<Extract<SetupAssistantKind, "google" | "slack"> | null>(null);

  const googleEnabled = serverConfig?.google_enabled ?? false;
  const slackServices = useMemo(
    () => services.filter((service) => service.id.startsWith("slack_")),
    [services],
  );
  const connectedSlackServices = useMemo(
    () => slackServices.filter((service) => service.connected),
    [slackServices],
  );
  const setupSlackServices = useMemo(
    () => slackServices.filter((service) => !service.connected),
    [slackServices],
  );
  const googleSummary = useMemo(
    () => googleConnectionSummary(googleEnabled, gmailAccounts),
    [gmailAccounts, googleEnabled],
  );
  const readyToolsCount =
    (googleSummary.tone === "ready" ? 1 : 0) + connectedSlackServices.length;

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextServices, nextGmail] = await Promise.all([
        listServicesApi(config),
        listGmailAccountsApi(config),
      ]);
      setServices(nextServices);
      setGmailAccounts(nextGmail);
      setLoadedOnce(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [config]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function toggleGoogle(enabled: boolean) {
    setPendingId("google");
    setError(null);
    try {
      await updateServerConfig({ integrations: { google: enabled } });
      await fetchServerConfig();
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPendingId(null);
    }
  }

  async function addGoogleAccount() {
    setPendingId("gmail:add");
    setError(null);
    try {
      await addGmailAccountApi(config);
      if (!googleEnabled) {
        await updateServerConfig({ integrations: { google: true } });
      }
      await fetchServerConfig();
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPendingId(null);
    }
  }

  async function removeGoogleAccount(account: GmailAccount) {
    setPendingId(`gmail:${account.token_file}`);
    setError(null);
    try {
      await removeGmailAccountApi(config, account.token_file);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPendingId(null);
    }
  }

  async function connectService(service: ServiceConnection) {
    if (!serviceKey.trim()) return;
    setPendingId(service.id);
    setError(null);
    try {
      await connectServiceApi(config, service.id, serviceKey.trim());
      setEditingId(null);
      setServiceKey("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPendingId(null);
    }
  }

  async function disconnectService(service: ServiceConnection) {
    setPendingId(service.id);
    setError(null);
    try {
      await disconnectServiceApi(config, service.id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPendingId(null);
    }
  }

  const hasLoadedData = loadedOnce || services.length > 0 || gmailAccounts.length > 0;
  const showContent = shouldShowLoadedSettingsContent({ loading, error, hasData: hasLoadedData });

  return (
    <div className="grid gap-5">
      <div className="flex items-start justify-between gap-3">
        <p className="m-0 text-sm text-muted leading-[1.45] max-w-[540px]">
          Connect the data and action providers ntrp can use as tools. Model providers stay in
          Providers; MCP servers stay in MCP.
        </p>
        <button
          type="button"
          onClick={() => void refresh()}
          disabled={loading}
          className="inline-flex items-center gap-1.5 h-8 px-2.5 rounded-md border border-line bg-surface text-sm text-ink-soft hover:border-line-strong transition-[border-color,scale] duration-check ease-out active:scale-[0.97] disabled:opacity-[0.45]"
        >
          <RefreshCw size={ICON.SM} strokeWidth={2} className={clsx(loading && "animate-spin")} />
          Refresh
        </button>
      </div>

      {error && (
        <SettingsInlineError
          title={settingsErrorTitle("integrations", hasLoadedData)}
          message={settingsErrorMessage(error)}
        />
      )}

      {loading && !hasLoadedData ? (
        <div className="text-sm text-muted">Loading integrations…</div>
      ) : !showContent ? (
        <SettingsConnectionHint />
      ) : (
        <>
          {assistant && (
            <SetupAssistant
              kind={assistant}
              onClose={() => setAssistant(null)}
              onDone={async () => {
                setAssistant(null);
                await fetchServerConfig();
                await refresh();
              }}
            />
          )}

          <ReadinessCard
            tone={readyToolsCount > 0 ? "ok" : "warn"}
            label={readyToolsCount > 0 ? "Tools ready" : "Connect tools"}
            detail={`Google: ${googleSummary.label} · Slack: ${connectedSlackServices.length || "none"}`}
            footnote="Tool integrations are optional, but connected tools become available to the agent."
          />

          <GoogleCard
            enabled={googleEnabled}
            summary={googleSummary}
            accounts={gmailAccounts}
            pendingId={pendingId}
            onToggle={toggleGoogle}
            onAdd={addGoogleAccount}
            onRemove={removeGoogleAccount}
            onAssistant={() => setAssistant("google")}
          />

          <ServiceCard
            connectedServices={connectedSlackServices}
            setupServices={setupSlackServices}
            editingId={editingId}
            serviceKey={serviceKey}
            pendingId={pendingId}
            onEdit={(service) => {
              setEditingId(service.id);
              setServiceKey("");
            }}
            onCancel={() => {
              setEditingId(null);
              setServiceKey("");
            }}
            onKeyChange={setServiceKey}
            onConnect={connectService}
            onDisconnect={disconnectService}
            onAssistant={() => setAssistant("slack")}
          />
        </>
      )}
    </div>
  );
}

function GoogleCard({
  enabled,
  summary,
  accounts,
  pendingId,
  onToggle,
  onAdd,
  onRemove,
  onAssistant,
}: {
  enabled: boolean;
  summary: GoogleConnectionSummary;
  accounts: GmailAccount[];
  pendingId: string | null;
  onToggle: (enabled: boolean) => Promise<void>;
  onAdd: () => Promise<void>;
  onRemove: (account: GmailAccount) => Promise<void>;
  onAssistant: () => void;
}) {
  const pendingGoogle = pendingId === "google";
  const pendingAdd = pendingId === "gmail:add";
  const summaryTone = {
    ready: "bg-ok-soft text-ok",
    paused: "bg-warn-soft text-warn",
    setup: "bg-surface-soft text-muted",
  }[summary.tone];

  return (
    <section className="rounded-[12px] border border-line-soft bg-surface overflow-hidden">
      <div className="flex flex-wrap items-start gap-3 px-3.5 py-3">
        <div className="min-w-[150px] flex-1 grid gap-1">
          <div className="flex items-center gap-2 min-w-0">
            <GoogleIcon enabled={enabled} />
            <div className="text-base font-medium text-ink truncate">Google Workspace</div>
            <span className={clsx("shrink-0 px-1.5 py-0.5 rounded-full text-2xs font-medium", summaryTone)}>
              {summary.label}
            </span>
          </div>
          <div className="text-xs text-muted leading-[1.4]">
            Gmail and Calendar share the same Google account token.
          </div>
          <div className="text-xs text-muted font-mono truncate">
            {summary.detail}
          </div>
        </div>

        <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
          <button
            type="button"
            onClick={onAssistant}
            className="h-8 px-2.5 rounded-md border border-line bg-surface text-sm text-ink-soft hover:border-line-strong transition-[border-color,scale] duration-check ease-out active:scale-[0.97]"
          >
            Run setup assistant
          </button>
          <button
            type="button"
            onClick={() => void onAdd()}
            disabled={pendingAdd}
            className="h-8 px-2.5 rounded-md border border-line bg-surface text-sm text-ink-soft hover:border-line-strong transition-[border-color,scale] duration-check ease-out active:scale-[0.97] disabled:opacity-[0.45]"
          >
            <BlurSwap swapKey={pendingAdd ? "connecting" : "add"} blur={2}>
              {pendingAdd ? "Connecting…" : "Add account"}
            </BlurSwap>
          </button>
          <button
            type="button"
            onClick={() => void onToggle(!enabled)}
            disabled={pendingGoogle}
            className={clsx(
              "h-8 px-3 rounded-md text-sm font-medium transition-[background-color,border-color,color,opacity,scale] duration-check ease-out active:scale-[0.97] disabled:opacity-[0.45]",
              enabled
                ? "border border-line bg-surface text-ink-soft hover:border-line-strong"
                : "bg-ink text-on-ink hover:opacity-90",
            )}
          >
            <BlurSwap swapKey={pendingGoogle ? "saving" : enabled ? "disable" : "enable"} blur={2}>
              {pendingGoogle ? "Saving…" : enabled ? "Disable" : "Enable"}
            </BlurSwap>
          </button>
        </div>
      </div>

      {accounts.length > 0 && (
        <div className="grid gap-1 px-3.5 py-2.5 bg-surface-soft/35">
          {accounts.map((account) => (
            <div
              key={account.token_file}
              className="grid grid-cols-[minmax(0,1fr)_auto] gap-2 items-center text-sm"
            >
              <div className="min-w-0">
                <div className="text-ink-soft truncate">{account.email || "Unknown account"}</div>
                <div
                  className={clsx(
                    "text-xs truncate",
                    account.error ? "text-bad" : "text-faint",
                  )}
                >
                  {account.error
                    ? account.error
                    : account.has_send_scope
                      ? "Read, send, and calendar access"
                      : "Read and calendar access"}
                </div>
              </div>
              <ConfirmDeleteButton
                size="md"
                label={`Remove ${account.email || account.token_file}`}
                busy={pendingId === `gmail:${account.token_file}`}
                onConfirm={() => void onRemove(account)}
              />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function ServiceCard({
  connectedServices,
  setupServices,
  editingId,
  serviceKey,
  pendingId,
  onEdit,
  onCancel,
  onKeyChange,
  onConnect,
  onDisconnect,
  onAssistant,
}: {
  connectedServices: ServiceConnection[];
  setupServices: ServiceConnection[];
  editingId: string | null;
  serviceKey: string;
  pendingId: string | null;
  onEdit: (service: ServiceConnection) => void;
  onCancel: () => void;
  onKeyChange: (value: string) => void;
  onConnect: (service: ServiceConnection) => Promise<void>;
  onDisconnect: (service: ServiceConnection) => Promise<void>;
  onAssistant: () => void;
}) {
  return (
    <section className="rounded-[12px] border border-line-soft bg-surface overflow-hidden">
      <div className="px-3.5 py-3 border-b border-line-soft">
        <div className="flex items-center gap-2">
          <MessageCircle size={ICON.MD} strokeWidth={2} className="text-muted" />
          <div className="text-base font-medium text-ink">Slack</div>
        </div>
        <div className="mt-1 text-xs text-muted leading-[1.4]">
          Token-backed Slack tools. OAuth MCP servers stay in the MCP tab.
        </div>
        <button
          type="button"
          onClick={onAssistant}
          className="mt-2 h-8 px-2.5 rounded-md border border-line bg-surface text-sm text-ink-soft hover:border-line-strong transition-[border-color,scale] duration-check ease-out active:scale-[0.97]"
        >
          Run setup assistant
        </button>
      </div>

      {connectedServices.length + setupServices.length === 0 ? (
        <div className="px-3.5 py-3 text-sm text-muted">No token-backed services are registered.</div>
      ) : (
        <div className="grid gap-3 px-3.5 py-3">
          <ServiceSection title="Ready" empty="No Slack tokens connected.">
            {connectedServices.map((service) => (
              <ServiceRow
                key={service.id}
                service={service}
                editing={editingId === service.id}
                serviceKey={editingId === service.id ? serviceKey : ""}
                pending={pendingId === service.id}
                onEdit={() => onEdit(service)}
                onCancel={onCancel}
                onKeyChange={onKeyChange}
                onConnect={() => void onConnect(service)}
                onDisconnect={() => void onDisconnect(service)}
              />
            ))}
          </ServiceSection>
          <ServiceSection title="Set up" empty="All Slack token services are connected.">
            {setupServices.map((service) => (
              <ServiceRow
                key={service.id}
                service={service}
                editing={editingId === service.id}
                serviceKey={editingId === service.id ? serviceKey : ""}
                pending={pendingId === service.id}
                onEdit={() => onEdit(service)}
                onCancel={onCancel}
                onKeyChange={onKeyChange}
                onConnect={() => void onConnect(service)}
                onDisconnect={() => void onDisconnect(service)}
              />
            ))}
          </ServiceSection>
        </div>
      )}
    </section>
  );
}

function ServiceSection({
  title,
  empty,
  children,
}: {
  title: string;
  empty: string;
  children: ReactNode;
}) {
  const childCount = Array.isArray(children) ? children.length : children ? 1 : 0;
  return (
    <section className="grid gap-2">
      <SectionHeader label={title} />
      {childCount > 0 ? (
        <div className="grid gap-2">{children}</div>
      ) : (
        <div className="rounded-[9px] border border-line-soft bg-surface-soft/45 px-3 py-2 text-sm text-muted">
          {empty}
        </div>
      )}
    </section>
  );
}

function ServiceRow({
  service,
  editing,
  serviceKey,
  pending,
  onEdit,
  onCancel,
  onKeyChange,
  onConnect,
  onDisconnect,
}: {
  service: ServiceConnection;
  editing: boolean;
  serviceKey: string;
  pending: boolean;
  onEdit: () => void;
  onCancel: () => void;
  onKeyChange: (value: string) => void;
  onConnect: () => void;
  onDisconnect: () => void;
}) {
  const actionLabel = pending ? "Working…" : serviceActionLabel(service);
  const readOnly = service.connected && service.from_env;
  const connectionPill = serviceConnectionPill(service);

  return (
    <div className="rounded-[10px] border border-line-soft bg-surface overflow-hidden">
      <div className="flex flex-wrap items-start gap-3 px-3 py-2.5">
        <div className="min-w-[150px] flex-1 grid gap-1">
          <div className="flex items-center gap-2 min-w-0">
            <ProviderDot connected={service.connected} />
            <div className="text-sm font-medium text-ink-soft truncate">{service.name}</div>
          </div>
          {connectionPill && <div className="text-xs text-muted font-mono truncate">{connectionPill}</div>}
        </div>
        <div className="ml-auto flex justify-end">
          {readOnly ? (
            <span className="inline-flex items-center h-8 px-3 rounded-md border border-line-soft bg-surface-soft text-sm font-medium text-muted">
              {actionLabel}
            </span>
          ) : (
            <button
              type="button"
              onClick={service.connected ? onDisconnect : onEdit}
              disabled={pending}
              className={clsx(
                "h-8 px-3 rounded-md text-sm font-medium transition-[background-color,border-color,color,opacity,scale] duration-check ease-out active:scale-[0.97] disabled:opacity-[0.45]",
                service.connected
                  ? "border border-line bg-surface text-ink-soft hover:border-line-strong"
                  : "bg-ink text-on-ink hover:opacity-90",
              )}
            >
              <BlurSwap swapKey={actionLabel} blur={2}>
                {actionLabel}
              </BlurSwap>
            </button>
          )}
        </div>
      </div>

      <AnimatePresence initial={false}>
        {editing && !service.connected && (
          <motion.div
            key="token-editor"
            initial={{ ...RISE_IN, y: -4 }}
            animate={RISE_SETTLED}
            exit={{ ...DISSOLVE_OUT, transition: { duration: MOTION.fast, ease: EASE_OUT } }}
            transition={{ duration: MOTION.row, ease: EASE_OUT }}
            className="grid grid-cols-[minmax(0,1fr)_auto_auto] gap-2 px-3 py-3 bg-surface-soft/35"
          >
            <input
              type="password"
              value={serviceKey}
              onChange={(event) => onKeyChange(event.target.value)}
              placeholder="Token"
              autoFocus
              className="input-field"
            />
            <button
              type="button"
              onClick={onConnect}
              disabled={!serviceKey.trim() || pending}
              className="h-9 px-3 rounded-[9px] bg-ink text-on-ink text-sm font-medium hover:opacity-90 disabled:opacity-[0.45] transition-[opacity,scale] duration-check ease-out active:scale-[0.97]"
            >
              Connect
            </button>
            <button
              type="button"
              onClick={onCancel}
              className="h-9 px-3 rounded-[9px] border border-line bg-surface text-sm text-muted hover:text-ink hover:border-line-strong transition-[color,border-color,scale] duration-check ease-out active:scale-[0.97]"
            >
              Cancel
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function GoogleIcon({ enabled }: { enabled: boolean }) {
  return (
    <span className="relative grid place-items-center w-4 h-4 shrink-0">
      <Mail size={ICON.MD} strokeWidth={2} className={enabled ? "text-ok" : "text-muted"} />
      <CalendarDays
        size={ICON.XS}
        strokeWidth={1.9}
        className={clsx("absolute -right-1 -bottom-0.5", enabled ? "text-ok" : "text-faint")}
      />
    </span>
  );
}

function ProviderDot({ connected }: { connected: boolean }) {
  if (connected) {
    return <CheckCircle2 size={ICON.MD} strokeWidth={2} className="text-ok shrink-0" />;
  }
  return <KeyRound size={ICON.MD} strokeWidth={2} className="text-faint shrink-0" />;
}
